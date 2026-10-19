"""Approach 4: a tiny MDM (master data management) hub in Python + DuckDB.

What an MDM hub does after the matching:
    - sequence-based master ids (customer_id) that remain stable during this database's lifetime
  - golden record per customer, built with survivorship rules, with field-level provenance
  - crosswalk (xref): source_system + source_record_id -> customer_id
  - history (SCD2) of every golden record version
  - review queue for the grey zone, and data-steward actions (approve / reject)
  - incremental matching of new records against the master, using the trained Splink model
  - GDPR erasure across master, crosswalk and history

Run 02_splink.py first (it writes results/clusters_splink.csv and results/splink_model.json).
Tables live in results/mdm.duckdb, so you can inspect them with any SQL client.
"""

import json
import logging
from collections import Counter
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
from splink import DuckDBAPI, Linker

sys.path.insert(0, str(Path(__file__).parent))
from common.standardise import standardise  # noqa: E402

HERE = Path(__file__).parent
RES = HERE / "results"
AUTO_MATCH, REVIEW = 0.95, 0.50
GOLDEN_FIELDS = [
    "first_name",
    "last_name",
    "dob",
    "email",
    "phone",
    "address",
    "city",
    "postcode",
]
SOURCE_PRIORITY = {"CRM": 1, "BILLING": 2, "WEB": 3}  # lower = more trusted
RECENCY_FIELDS = {
    "email",
    "phone",
    "address",
    "city",
    "postcode",
}  # contact data: latest wins
MODEL_COLUMNS = [
    "unique_id",
    "source_system",
    "first_name",
    "first_name_canon",
    "last_name",
    "dob",
    "email",
    "phone",
    "postcode",
    "postcode_area",
    "address",
    "surname_metaphone",
    "first_metaphone",
    "updated_at",
]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MiniMDM:
    def __init__(self, path: Path):
        self.con = duckdb.connect(str(path))
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS source_record (
                source_record_id VARCHAR PRIMARY KEY, source_system VARCHAR, first_name VARCHAR,
                last_name VARCHAR, dob VARCHAR, email VARCHAR, phone VARCHAR, address VARCHAR,
                city VARCHAR, postcode VARCHAR, updated_at VARCHAR, loaded_at VARCHAR);
            CREATE TABLE IF NOT EXISTS xref (
                source_record_id VARCHAR PRIMARY KEY, customer_id VARCHAR, match_probability DOUBLE,
                match_method VARCHAR, linked_at VARCHAR);
            CREATE TABLE IF NOT EXISTS golden_record (
                customer_id VARCHAR PRIMARY KEY, first_name VARCHAR, last_name VARCHAR, dob VARCHAR,
                email VARCHAR, phone VARCHAR, address VARCHAR, city VARCHAR, postcode VARCHAR,
                n_source_records INTEGER, sources VARCHAR, provenance JSON, version INTEGER, updated_at VARCHAR);
            CREATE TABLE IF NOT EXISTS golden_history AS SELECT *, NULL::VARCHAR AS valid_to
                FROM golden_record WHERE false;
            CREATE TABLE IF NOT EXISTS review_queue (
                source_record_id VARCHAR, candidate_customer_id VARCHAR, match_probability DOUBLE,
                status VARCHAR, created_at VARCHAR);
            CREATE TABLE IF NOT EXISTS steward_audit (
                action VARCHAR, source_record_id VARCHAR, from_customer_id VARCHAR, to_customer_id VARCHAR,
                reason VARCHAR, acted_at VARCHAR);
            CREATE SEQUENCE IF NOT EXISTS customer_seq START 1;
        """)

    # ---------- ids ----------
    def new_customer_id(self) -> str:
        """Allocate the next master ID from the persistent DuckDB sequence."""
        return f"C{self.con.execute('SELECT nextval(%s)' % repr('customer_seq')).fetchone()[0]:07d}"

    # ---------- survivorship ----------
    @staticmethod
    def survive(records: list[dict]) -> tuple[dict, dict]:
        """Pick each golden field from the member records. Returns (values, provenance).
        Plain python on purpose: it runs once per customer, pandas per group is too slow.
        """
        values, prov = {}, {}
        for f in GOLDEN_FIELDS:
            cand = [
                r
                for r in records
                if r[f] is not None and not pd.isna(r[f]) and str(r[f]).strip()
            ]
            if not cand:
                values[f], prov[f] = None, None
                continue
            if f in RECENCY_FIELDS:
                best = max(
                    cand,
                    key=lambda r: (
                        r["updated_at"],
                        -SOURCE_PRIORITY[r["source_system"]],
                    ),
                )
                rule = "most_recent"
            else:
                # names / dob: most frequent value across sources, ties -> trusted source, then recent
                freq = Counter(str(r[f]).lower() for r in cand)
                best = max(
                    cand,
                    key=lambda r: (
                        freq[str(r[f]).lower()],
                        -SOURCE_PRIORITY[r["source_system"]],
                        r["updated_at"],
                    ),
                )
                rule = "most_frequent_then_source_priority"
            values[f] = best[f]
            prov[f] = {
                "source_record_id": best["source_record_id"],
                "source": best["source_system"],
                "rule": rule,
            }
        return values, prov

    def rebuild_golden(self, customer_ids):
        """Recompute touched customers and append SCD2 snapshots from current xref membership."""
        ids = pd.DataFrame({"customer_id": sorted(set(customer_ids))})
        self.con.register("ids", ids)
        members = self.con.execute("""
            SELECT x.customer_id, s.* FROM source_record s JOIN xref x USING (source_record_id)
            JOIN ids USING (customer_id)""").df()
        old = self.con.execute(
            "SELECT customer_id, version FROM golden_record JOIN ids USING (customer_id)"
        ).df()
        old_version = dict(zip(old.customer_id, old.version))
        ts = now()
        rows = []
        grouped: dict[str, list[dict]] = {}
        for rec in members.to_dict("records"):
            grouped.setdefault(rec["customer_id"], []).append(rec)
        for cid, recs in grouped.items():
            vals, prov = self.survive(recs)
            rows.append(
                {
                    "customer_id": cid,
                    **{k: (None if pd.isna(v) else str(v)) for k, v in vals.items()},
                    "n_source_records": len(recs),
                    "sources": ",".join(sorted({r["source_system"] for r in recs})),
                    "provenance": json.dumps(prov),
                    "version": int(old_version.get(cid, 0)) + 1,
                    "updated_at": ts,
                }
            )
        # close previous versions, replace current ones (customers with no members left just disappear)
        self.con.execute(
            "UPDATE golden_history SET valid_to = ? WHERE valid_to IS NULL AND customer_id IN (SELECT customer_id FROM ids)",
            [ts],
        )
        self.con.execute(
            "DELETE FROM golden_record WHERE customer_id IN (SELECT customer_id FROM ids)"
        )
        self.con.unregister("ids")
        if rows:
            new = pd.DataFrame(rows)
            self.con.register("new_golden", new)
            self.con.execute("INSERT INTO golden_record SELECT * FROM new_golden")
            self.con.execute(
                "INSERT INTO golden_history SELECT *, NULL FROM new_golden"
            )
            self.con.unregister("new_golden")

    def _close_history(self, cid):
        self.con.execute(
            "UPDATE golden_history SET valid_to = ? WHERE customer_id = ? AND valid_to IS NULL",
            [now(), cid],
        )

    # ---------- loading ----------
    def insert_sources(self, raw: pd.DataFrame):
        """Standardize incoming attributes and persist source rows without changing their IDs."""
        cols = [
            "source_record_id",
            "source_system",
            "first_name",
            "last_name",
            "dob",
            "email",
            "phone",
            "address",
            "city",
            "postcode",
            "updated_at",
        ]
        # keep the cleansed values (same standardisation as the matcher), so golden records are tidy
        clean = standardise(raw)
        df = raw[cols].copy()
        for c in ["email", "phone", "postcode", "dob"]:
            df[c] = clean[c]
        for c in ["first_name", "last_name"]:
            df[c] = clean[c].str.title()
        df = df.assign(loaded_at=now())
        self.con.register("incoming", df)
        self.con.execute("INSERT INTO source_record SELECT * FROM incoming")
        self.con.unregister("incoming")

    def link(self, source_record_id, customer_id, prob, method):
        """Upsert the crosswalk assignment and its match confidence and method."""
        self.con.execute(
            "INSERT OR REPLACE INTO xref VALUES (?, ?, ?, ?, ?)",
            [source_record_id, customer_id, prob, method, now()],
        )

    def initial_load(self, raw: pd.DataFrame, clusters: pd.DataFrame):
        """Create the initial source, crosswalk, and golden-record tables from batch clusters."""
        self.insert_sources(raw)
        cluster_to_customer = {
            c: self.new_customer_id() for c in clusters.cluster_id.unique()
        }
        xref = clusters.assign(
            customer_id=clusters.cluster_id.map(cluster_to_customer),
            match_probability=None,
            match_method="splink_batch_cluster",
            linked_at=now(),
        )
        xref = xref.rename(columns={"unique_id": "source_record_id"})[
            [
                "source_record_id",
                "customer_id",
                "match_probability",
                "match_method",
                "linked_at",
            ]
        ]
        self.con.register("x", xref)
        self.con.execute("INSERT INTO xref SELECT * FROM x")
        self.con.unregister("x")
        self.rebuild_golden(list(cluster_to_customer.values()))

    def incremental_load(self, raw_new: pd.DataFrame, pairs: pd.DataFrame):
        """Attach, review, or create a customer for each new record using scored candidate pairs.

        `pairs` contains `unique_id_l` (existing), `unique_id_r` (new), and
        `match_probability` columns from `score_new_records()`.
        """
        self.insert_sources(raw_new)
        xref = (
            self.con.execute("SELECT source_record_id, customer_id FROM xref")
            .df()
            .set_index("source_record_id")
        )
        pairs = pairs.assign(customer_id=pairs.unique_id_l.map(xref.customer_id))
        best = (
            pairs.sort_values("match_probability", ascending=False)
            .drop_duplicates("unique_id_r")
            .set_index("unique_id_r")
        )
        touched, stats = set(), {"auto_linked": 0, "to_review": 0, "new_customer": 0}
        for rid in raw_new.source_record_id:
            if rid in best.index and best.loc[rid, "match_probability"] >= AUTO_MATCH:
                cid, p = best.loc[rid, "customer_id"], float(
                    best.loc[rid, "match_probability"]
                )
                self.link(rid, cid, p, "splink_incremental_auto")
                stats["auto_linked"] += 1
            else:
                cid = (
                    self.new_customer_id()
                )  # new customer until a steward says otherwise
                self.link(rid, cid, None, "new_customer")
                stats["new_customer"] += 1
                if rid in best.index and best.loc[rid, "match_probability"] >= REVIEW:
                    self.con.execute(
                        "INSERT INTO review_queue VALUES (?, ?, ?, 'open', ?)",
                        [
                            rid,
                            best.loc[rid, "customer_id"],
                            float(best.loc[rid, "match_probability"]),
                            now(),
                        ],
                    )
                    stats["to_review"] += 1
            touched.add(cid)
        self.rebuild_golden(touched)
        return stats

    # ---------- data steward actions ----------
    def approve_review(self, source_record_id):
        """Move the temporary customer's records to the reviewed candidate and rebuild both."""
        cid_new, cid_target = self.con.execute(
            """
            SELECT x.customer_id, r.candidate_customer_id FROM review_queue r JOIN xref x USING (source_record_id)
            WHERE r.source_record_id = ? AND r.status = 'open'""",
            [source_record_id],
        ).fetchone()
        self.con.execute(
            "UPDATE xref SET customer_id = ?, match_method = 'steward_approved', linked_at = ? "
            "WHERE customer_id = ?",
            [cid_target, now(), cid_new],
        )
        self.con.execute(
            "UPDATE review_queue SET status = 'approved' WHERE source_record_id = ?",
            [source_record_id],
        )
        self.rebuild_golden(
            [cid_new, cid_target]
        )  # cid_new disappears (merged), target gets a new version

    def reject_review(self, source_record_id):
        """Mark an open candidate as rejected while leaving its current customer assignment intact."""
        self.con.execute(
            "UPDATE review_queue SET status = 'rejected' WHERE source_record_id = ?",
            [source_record_id],
        )

    def unmerge_record(self, source_record_id, reason):
        """Move one source record to a new customer, retaining history and steward audit."""
        if not reason or not reason.strip():
            raise ValueError("A reason is required to un-merge a source record")
        row = self.con.execute(
            "SELECT customer_id FROM xref WHERE source_record_id = ?",
            [source_record_id],
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown source record: {source_record_id}")

        old_customer_id = row[0]
        member_count = self.con.execute(
            "SELECT count(*) FROM xref WHERE customer_id = ?", [old_customer_id]
        ).fetchone()[0]
        if member_count < 2:
            raise ValueError(
                f"Customer {old_customer_id} has no other records to split from"
            )
        new_customer_id = self.new_customer_id()
        acted_at = now()
        self.con.execute("BEGIN TRANSACTION")
        try:
            self.con.execute(
                "UPDATE xref SET customer_id = ?, match_probability = NULL, "
                "match_method = 'steward_unmerged', linked_at = ? WHERE source_record_id = ?",
                [new_customer_id, acted_at, source_record_id],
            )
            self.con.execute(
                "UPDATE review_queue SET status = 'unmerged' WHERE source_record_id = ?",
                [source_record_id],
            )
            self.con.execute(
                "INSERT INTO steward_audit VALUES ('unmerge', ?, ?, ?, ?, ?)",
                [source_record_id, old_customer_id, new_customer_id, reason, acted_at],
            )
            self.rebuild_golden([old_customer_id, new_customer_id])
            self.con.execute("COMMIT")
        except Exception:
            self.con.execute("ROLLBACK")
            raise
        return new_customer_id

    def erase_customer(self, customer_id):
        """Remove a customer's source data, crosswalk, current golden record, and history."""
        ids = [
            r[0]
            for r in self.con.execute(
                "SELECT source_record_id FROM xref WHERE customer_id = ?", [customer_id]
            ).fetchall()
        ]
        for t, col, vals in [
            ("source_record", "source_record_id", ids),
            ("review_queue", "source_record_id", ids),
        ]:
            if vals:
                self.con.execute(
                    f"DELETE FROM {t} WHERE {col} IN ({','.join('?' * len(vals))})",
                    vals,
                )
        for t in ["xref", "golden_record", "golden_history"]:
            self.con.execute(f"DELETE FROM {t} WHERE customer_id = ?", [customer_id])
        return len(ids)


def score_new_records(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Score new-versus-existing records with the saved Splink model, without retraining."""
    db_api = DuckDBAPI()
    sdf_existing = db_api.register(existing[MODEL_COLUMNS], table_name="existing")
    sdf_new = db_api.register(new[MODEL_COLUMNS], table_name="new_records")
    linker = Linker(
        sdf_existing, str(RES / "splink_model.json"), log_level=logging.WARNING
    )
    for col in ["first_name_canon", "last_name", "email"]:
        linker.table_management.compute_tf_table(col)
    preds = linker.inference.predict_between(
        sdf_existing, sdf_new, threshold_match_probability=REVIEW
    )
    return preds.as_pandas_dataframe()[
        ["unique_id_l", "unique_id_r", "match_probability"]
    ]


def main():
    """Rebuild the demo database, demonstrate incremental MDM actions, and export tables.

    This presentation entry point intentionally deletes the prior DuckDB file first;
    use `MiniMDM` directly when testing persistence across process runs.
    """
    db_path = RES / "mdm.duckdb"
    db_path.unlink(missing_ok=True)
    mdm = MiniMDM(db_path)

    raw = pd.read_csv(HERE / "data/customers.csv", dtype=str)
    clusters = pd.read_csv(RES / "clusters_splink.csv")
    mdm.initial_load(raw, clusters)
    print(
        "initial load:",
        mdm.con.execute(
            "SELECT count(*) customers, sum(n_source_records) records FROM golden_record"
        ).fetchone(),
    )

    # incremental batch
    raw_new = pd.read_csv(HERE / "data/new_batch.csv", dtype=str)
    pairs = score_new_records(standardise(raw), standardise(raw_new))
    stats = mdm.incremental_load(raw_new, pairs)
    print("incremental batch:", stats)

    # how good were the incremental decisions? (truth only used here)
    truth = pd.concat([raw, raw_new]).set_index("source_record_id")["true_entity_id"]
    x = (
        mdm.con.execute("SELECT source_record_id, customer_id FROM xref")
        .df()
        .set_index("source_record_id")
    )
    x["true"] = truth
    cust_truth = (
        x.loc[raw.source_record_id]
        .groupby("customer_id")["true"]
        .agg(lambda s: s.mode()[0])
    )
    new = x.loc[raw_new.source_record_id]
    existing_people = set(raw.true_entity_id)
    ok_link = sum(
        1
        for rid, r in new.iterrows()
        if r.true in existing_people and cust_truth.get(r.customer_id) == r.true
    )
    should_link = sum(1 for _, r in new.iterrows() if r.true in existing_people)
    wrong_link = sum(
        1
        for _, r in new.iterrows()
        if r.customer_id in cust_truth and cust_truth[r.customer_id] != r.true
    )
    print(
        f"returning customers correctly attached: {ok_link}/{should_link}, wrong attachments: {wrong_link}"
    )

    # steward approves the first open review item; GDPR erase one customer
    first = mdm.con.execute(
        "SELECT source_record_id FROM review_queue WHERE status='open' LIMIT 1"
    ).fetchone()
    if first:
        mdm.approve_review(first[0])
        print("steward approved review item", first[0])
    victim = mdm.con.execute(
        "SELECT customer_id FROM golden_record ORDER BY n_source_records DESC LIMIT 1"
    ).fetchone()[0]
    print(f"GDPR erase {victim}: removed {mdm.erase_customer(victim)} source records")

    # exports
    mdm.con.execute("SELECT * FROM golden_record ORDER BY customer_id").df().to_csv(
        RES / "mdm_golden_record.csv", index=False
    )
    mdm.con.execute("SELECT * FROM xref ORDER BY customer_id").df().to_csv(
        RES / "mdm_xref.csv", index=False
    )
    mdm.con.execute("SELECT * FROM review_queue").df().to_csv(
        RES / "mdm_review_queue.csv", index=False
    )
    ex = (
        mdm.con.execute(
            "SELECT * FROM golden_record WHERE n_source_records >= 3 AND phone IS NOT NULL LIMIT 1"
        )
        .df()
        .iloc[0]
    )
    print("\nexample golden record:\n", ex.drop("provenance").to_string())
    print("provenance:", json.dumps(json.loads(ex.provenance), indent=1)[:600])
    mdm.con.close()


if __name__ == "__main__":
    main()
