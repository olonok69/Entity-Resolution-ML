"""Approach 4: a tiny MDM (master data management) hub in Python + DuckDB.

What an MDM hub does after the matching:
    - sequence-based master ids (customer_id) that remain stable during this database's lifetime
  - golden record per customer, built with survivorship rules, with field-level provenance
  - crosswalk (xref): source_system + source_record_id -> customer_id
  - history (SCD2) of every golden record version
  - review queue for the grey zone, and data-steward actions (approve / reject)
  - incremental matching of new records against the master, using the trained Splink model
  - GDPR erasure across master, crosswalk and history

Run 02_splink.py first (it writes results/splink_model.json) and 04_graph_resolution.py
(it writes results/clusters_graph.csv, the Splink clusters after cannot-link repair; without
it the plain results/clusters_splink.csv is used).
Tables live in results/mdm.duckdb, so you can inspect them with any SQL client.

Inputs:
  - data/customers.csv: the initial 8,192 source records (CRM, BILLING, WEB).
  - results/clusters_graph.csv (or results/clusters_splink.csv): unique_id -> cluster_id,
    the batch matching result that seeds the master.
  - results/splink_model.json: the trained Splink model, reused to score the new batch.
  - data/new_batch.csv: a later delivery of records, some from returning customers.

Outputs:
  - results/mdm.duckdb: the hub database (source_record, xref, golden_record,
    golden_history, review_queue, steward_audit).
  - results/mdm_golden_record.csv, results/mdm_xref.csv, results/mdm_review_queue.csv.

How to run (from er-demo/):  python 05_mdm.py
Related slides: 18 (Section Mastering), 19 (Mini MDM), 13 (Precision or recall, for the
auto-match and review thresholds). DEMO_GUIDE.md sections 3.8 and 4 (step 5).
"""

# Standard library: json for the provenance column, logging to quieten Splink,
# Counter for "most frequent value" survivorship, datetime for timestamps.
import json
import logging
from collections import Counter
import sys
from datetime import datetime, timezone
from pathlib import Path

# DuckDB is an embedded SQL database stored in one file; it plays the role of the MDM hub.
import duckdb
import pandas as pd
# DuckDBAPI tells Splink to run its SQL on DuckDB; Linker loads a saved model and predicts.
from splink import DuckDBAPI, Linker

# Make the er-demo folder importable so the shared "common" package can be found
# no matter which directory the script is launched from.
sys.path.insert(0, str(Path(__file__).parent))
# The same cleansing used by the matchers, so the hub stores values in matcher format.
from common.standardise import standardise  # noqa: E402

# Folder of this script, and the results folder written by the earlier steps.
HERE = Path(__file__).parent
RES = HERE / "results"
# Decision thresholds on Splink's match probability for an incoming record:
# p >= 0.95 is attached automatically, 0.50 <= p < 0.95 is the grey zone a steward reviews,
# and anything lower becomes a new customer. Raising AUTO_MATCH favours precision
# (fewer false merges), lowering it favours recall (slide 13).
AUTO_MATCH, REVIEW = 0.95, 0.50
# The attributes the golden record carries. Each one is chosen independently by survivorship.
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
# Source trust ranking used to break ties: the CRM is curated by staff, web forms are
# self-typed, so a CRM value is preferred when everything else is equal.
SOURCE_PRIORITY = {"CRM": 1, "BILLING": 2, "WEB": 3}  # lower = more trusted
# Fields that legitimately change over a customer's life (people move, change phone),
# so the most recently updated value is the best guess of the current truth.
RECENCY_FIELDS = {
    "email",
    "phone",
    "address",
    "city",
    "postcode",
}  # contact data: latest wins
# Exactly the columns the saved Splink model expects in its input tables. The model's
# comparisons and blocking rules refer to these (including derived columns such as
# first_name_canon and the metaphone codes that standardise() adds).
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
    # Current UTC time as an ISO 8601 string (e.g. 2026-10-24T06:57:40+00:00).
    # Every link, version and audit row is stamped with it.
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MiniMDM:
    """A consolidation-style MDM hub: matching results go in, golden records come out."""

    def __init__(self, path: Path):
        # Open (or create) the DuckDB database file that holds all hub tables.
        self.con = duckdb.connect(str(path))
        # Keep source rows and the source-to-master crosswalk separate from the
        # derived golden record, so assignments and survivorship can be inspected.
        # Table roles:
        #   source_record  - cleansed copy of every source row, keyed by its source id.
        #   xref           - the crosswalk: which master customer each source row belongs to,
        #                    with the probability and method that put it there.
        #   golden_record  - the current best version of each customer (one row each).
        #   golden_history - SCD2 (slowly changing dimension type 2) history: every version
        #                    of every golden record, with valid_to NULL for the current one.
        #                    It is created with the same columns as golden_record plus valid_to,
        #                    by selecting zero rows ("WHERE false") to copy just the schema.
        #   review_queue   - grey-zone candidates waiting for a data steward.
        #   steward_audit  - who changed what and why (un-merges), for accountability.
        #   customer_seq   - a persistent counter that hands out master ids.
        # IF NOT EXISTS makes the constructor safe to call on an existing database.
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
        # The SQL becomes SELECT nextval('customer_seq'); the number is zero-padded to
        # 7 digits, giving ids like C0000001. A sequence never reuses a value, so a master
        # id is never handed to a second customer, even after a merge or erasure.
        return f"C{self.con.execute('SELECT nextval(%s)' % repr('customer_seq')).fetchone()[0]:07d}"

    # ---------- survivorship ----------
    @staticmethod
    def survive(records: list[dict]) -> tuple[dict, dict]:
        """Pick each golden field from the member records. Returns (values, provenance).
        Plain python on purpose: it runs once per customer, pandas per group is too slow.
        """
        # values: field -> winning value; prov: field -> which record and rule won it.
        values, prov = {}, {}
        # Each field is decided on its own, so a golden record can mix the name from
        # one source with the phone from another.
        for f in GOLDEN_FIELDS:
            # Empty values cannot win survivorship. A field with no usable source
            # remains null and has no provenance entry.
            # pd.isna catches NaN from pandas; strip() rejects blank strings.
            cand = [
                r
                for r in records
                if r[f] is not None and not pd.isna(r[f]) and str(r[f]).strip()
            ]
            # No member has a value: store null, and null provenance.
            if not cand:
                values[f], prov[f] = None, None
                continue
            if f in RECENCY_FIELDS:
                # Contact details can change over time; use the latest source value,
                # with source trust as a deterministic tie-breaker.
                # max() compares the key tuples left to right: first updated_at (ISO strings
                # sort chronologically), then the negated priority so CRM (1) beats WEB (3).
                best = max(
                    cand,
                    key=lambda r: (
                        r["updated_at"],
                        -SOURCE_PRIORITY[r["source_system"]],
                    ),
                )
                rule = "most_recent"
            else:
                # Names and DOB are less volatile: choose the value supported most
                # often, then prefer the trusted source and the most recent record.
                # Counter counts each value case-insensitively, so "SMITH" and "Smith" vote together.
                freq = Counter(str(r[f]).lower() for r in cand)
                # Key tuple: (how many records agree, source trust, recency). A typo that
                # appears once loses to the spelling two sources share.
                best = max(
                    cand,
                    key=lambda r: (
                        freq[str(r[f]).lower()],
                        -SOURCE_PRIORITY[r["source_system"]],
                        r["updated_at"],
                    ),
                )
                rule = "most_frequent_then_source_priority"
            # Keep the winning value and record its lineage, so every golden value
            # can be explained back to a source row and a rule.
            values[f] = best[f]
            prov[f] = {
                "source_record_id": best["source_record_id"],
                "source": best["source_system"],
                "rule": rule,
            }
        return values, prov

    def rebuild_golden(self, customer_ids):
        """Recompute touched customers and append SCD2 snapshots from current xref membership."""
        # Put the touched ids in a one-column DataFrame and register it, so DuckDB can
        # join against it like a table named "ids" (register exposes pandas data to SQL).
        ids = pd.DataFrame({"customer_id": sorted(set(customer_ids))})
        self.con.register("ids", ids)
        # All source rows currently linked to the touched customers, with their customer_id.
        # USING (col) joins on a column with the same name in both tables.
        members = self.con.execute("""
            SELECT x.customer_id, s.* FROM source_record s JOIN xref x USING (source_record_id)
            JOIN ids USING (customer_id)""").df()
        # Current version number of each touched customer, so the new snapshot is version + 1.
        old = self.con.execute(
            "SELECT customer_id, version FROM golden_record JOIN ids USING (customer_id)"
        ).df()
        old_version = dict(zip(old.customer_id, old.version))
        # One timestamp for the whole rebuild: it closes old versions and stamps new ones.
        ts = now()
        rows = []
        # Group member rows by customer as lists of dicts (fast plain-python input for survive).
        grouped: dict[str, list[dict]] = {}
        for rec in members.to_dict("records"):
            grouped.setdefault(rec["customer_id"], []).append(rec)
        for cid, recs in grouped.items():
            # Rebuild only affected customers after a new link, approval, or un-merge.
            vals, prov = self.survive(recs)
            # One golden row: survived values as strings (NaN becomes None), how many
            # source rows and which systems back it, the provenance as JSON text,
            # and the next version number (1 for a brand new customer).
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
        # Close the current SCD2 rows before replacing them with the recomputed snapshots.
        # A customer with no remaining source records has no replacement golden row.
        self.con.execute(
            "UPDATE golden_history SET valid_to = ? WHERE valid_to IS NULL AND customer_id IN (SELECT customer_id FROM ids)",
            [ts],
        )
        # Drop the current golden rows of touched customers; they are re-inserted below.
        # A customer emptied by a merge stays deleted, which is how a merged-away id retires.
        self.con.execute(
            "DELETE FROM golden_record WHERE customer_id IN (SELECT customer_id FROM ids)"
        )
        self.con.unregister("ids")
        if rows:
            # Insert the new snapshots as the current golden records and as open
            # (valid_to NULL) history rows. Column order matches the table definitions.
            new = pd.DataFrame(rows)
            self.con.register("new_golden", new)
            self.con.execute("INSERT INTO golden_record SELECT * FROM new_golden")
            self.con.execute(
                "INSERT INTO golden_history SELECT *, NULL FROM new_golden"
            )
            self.con.unregister("new_golden")

    def _close_history(self, cid):
        # Helper to end the open history version of one customer. Not called in the
        # demo flow (rebuild_golden closes versions itself); kept for manual use.
        self.con.execute(
            "UPDATE golden_history SET valid_to = ? WHERE customer_id = ? AND valid_to IS NULL",
            [now(), cid],
        )

    # ---------- loading ----------
    def insert_sources(self, raw: pd.DataFrame):
        """Standardize incoming attributes and persist source rows without changing their IDs."""
        # The source columns the hub keeps (truth labels such as true_entity_id are left out).
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
        # Replace identifiers with their cleansed form (lower-case email, digits-only phone,
        # spaced postcode, ISO date) so survivorship compares like with like.
        for c in ["email", "phone", "postcode", "dob"]:
            df[c] = clean[c]
        # Cleansed names are lower case for matching; title case reads better in a master record.
        for c in ["first_name", "last_name"]:
            df[c] = clean[c].str.title()
        # Stamp when the hub received the rows (separate from the source's own updated_at).
        df = df.assign(loaded_at=now())
        # Bulk insert the DataFrame through a registered view.
        self.con.register("incoming", df)
        self.con.execute("INSERT INTO source_record SELECT * FROM incoming")
        self.con.unregister("incoming")

    def link(self, source_record_id, customer_id, prob, method):
        """Upsert the crosswalk assignment and its match confidence and method."""
        # INSERT OR REPLACE overwrites an existing row with the same primary key, so a
        # source record always has exactly one current customer.
        self.con.execute(
            "INSERT OR REPLACE INTO xref VALUES (?, ?, ?, ?, ?)",
            [source_record_id, customer_id, prob, method, now()],
        )

    def initial_load(self, raw: pd.DataFrame, clusters: pd.DataFrame):
        """Create the initial source, crosswalk, and golden-record tables from batch clusters."""
        # 1. Store the cleansed source rows.
        self.insert_sources(raw)
        # 2. Give every batch cluster its own master id. Cluster ids are only labels from
        #    one matching run; the customer_id is the stable key the business will use.
        cluster_to_customer = {
            c: self.new_customer_id() for c in clusters.cluster_id.unique()
        }
        # 3. Build the crosswalk: every source record points to its cluster's customer_id.
        #    Batch clusters have no single pair probability, so it is left empty.
        xref = clusters.assign(
            customer_id=clusters.cluster_id.map(cluster_to_customer),
            match_probability=None,
            match_method="splink_batch_cluster",
            linked_at=now(),
        )
        # Rename to the hub's column name and keep the xref columns in table order.
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
        # 4. Build version 1 of every golden record.
        self.rebuild_golden(list(cluster_to_customer.values()))

    def incremental_load(self, raw_new: pd.DataFrame, pairs: pd.DataFrame):
        """Attach, review, or create a customer for each new record using scored candidate pairs.

        `pairs` contains `unique_id_l` (existing), `unique_id_r` (new), and
        `match_probability` columns from `score_new_records()`.
        """
        # Store the new rows first so rebuild_golden can see them.
        self.insert_sources(raw_new)
        # Current crosswalk as a lookup: source_record_id -> customer_id.
        xref = (
            self.con.execute("SELECT source_record_id, customer_id FROM xref")
            .df()
            .set_index("source_record_id")
        )
        # Translate each candidate's existing source record into its master customer.
        # The new record is compared to records, but it is attached to a customer.
        pairs = pairs.assign(customer_id=pairs.unique_id_l.map(xref.customer_id))
        # Keep only the strongest candidate per incoming record; lower-ranked candidates
        # are not attached automatically, but the strongest grey-zone candidate is reviewable.
        # Sorting by probability descending and then drop_duplicates keeps the first
        # (highest) row for each new record id.
        best = (
            pairs.sort_values("match_probability", ascending=False)
            .drop_duplicates("unique_id_r")
            .set_index("unique_id_r")
        )
        # touched: customers whose golden record must be rebuilt; stats: printed counts.
        touched, stats = set(), {"auto_linked": 0, "to_review": 0, "new_customer": 0}
        for rid in raw_new.source_record_id:
            # Confident match: attach the record to the existing customer.
            if rid in best.index and best.loc[rid, "match_probability"] >= AUTO_MATCH:
                cid, p = best.loc[rid, "customer_id"], float(
                    best.loc[rid, "match_probability"]
                )
                self.link(rid, cid, p, "splink_incremental_auto")
                stats["auto_linked"] += 1
            else:
                # A non-auto-linked record gets its own provisional master ID, avoiding
                # a risky merge while a steward reviews candidates in the review band.
                cid = (
                    self.new_customer_id()
                )  # new customer until a steward says otherwise
                self.link(rid, cid, None, "new_customer")
                stats["new_customer"] += 1
                # Grey zone (0.50 <= p < 0.95): also queue the best candidate for a human.
                # Records with no candidate or p < 0.50 are just new customers.
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
        # One rebuild for all affected customers: attached-to customers get a new version,
        # new customers get version 1.
        self.rebuild_golden(touched)
        return stats

    # ---------- data steward actions ----------
    def approve_review(self, source_record_id):
        """Move the temporary customer's records to the reviewed candidate and rebuild both."""
        # Look up the provisional customer the record sits in now, and the candidate the
        # steward agreed with. Only open items are eligible.
        cid_new, cid_target = self.con.execute(
            """
            SELECT x.customer_id, r.candidate_customer_id FROM review_queue r JOIN xref x USING (source_record_id)
            WHERE r.source_record_id = ? AND r.status = 'open'""",
            [source_record_id],
        ).fetchone()
        # Re-point every record of the provisional customer to the target (a merge),
        # marking that a human made the decision.
        self.con.execute(
            "UPDATE xref SET customer_id = ?, match_method = 'steward_approved', linked_at = ? "
            "WHERE customer_id = ?",
            [cid_target, now(), cid_new],
        )
        # Close the review item. Steward decisions like this are future training labels.
        self.con.execute(
            "UPDATE review_queue SET status = 'approved' WHERE source_record_id = ?",
            [source_record_id],
        )
        self.rebuild_golden(
            [cid_new, cid_target]
        )  # cid_new disappears (merged), target gets a new version

    def reject_review(self, source_record_id):
        """Mark an open candidate as rejected while leaving its current customer assignment intact."""
        # The record already lives in its own provisional customer, so rejecting only
        # updates the queue status; no xref or golden record change is needed.
        self.con.execute(
            "UPDATE review_queue SET status = 'rejected' WHERE source_record_id = ?",
            [source_record_id],
        )

    def unmerge_record(self, source_record_id, reason):
        """Move one source record to a new customer, retaining history and steward audit."""
        # Guard rails: an un-merge must be justified, the record must exist, and it must
        # share its customer with at least one other record (otherwise there is nothing to split).
        if not reason or not reason.strip():
            raise ValueError("A reason is required to un-merge a source record")
        row = self.con.execute(
            "SELECT customer_id FROM xref WHERE source_record_id = ?",
            [source_record_id],
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown source record: {source_record_id}")

        old_customer_id = row[0]
        # How many source records the current customer holds.
        member_count = self.con.execute(
            "SELECT count(*) FROM xref WHERE customer_id = ?", [old_customer_id]
        ).fetchone()[0]
        if member_count < 2:
            raise ValueError(
                f"Customer {old_customer_id} has no other records to split from"
            )
        # The split-off record gets a fresh master id.
        new_customer_id = self.new_customer_id()
        acted_at = now()
        # A transaction makes the changes all-or-nothing: if any step fails, ROLLBACK
        # undoes the others so the hub never shows a half-done un-merge.
        self.con.execute("BEGIN TRANSACTION")
        try:
            # Crosswalk, review status, audit event, and both golden records change together.
            # Move the record; its old probability no longer applies.
            self.con.execute(
                "UPDATE xref SET customer_id = ?, match_probability = NULL, "
                "match_method = 'steward_unmerged', linked_at = ? WHERE source_record_id = ?",
                [new_customer_id, acted_at, source_record_id],
            )
            # If the record came through review, record that the decision was reversed.
            self.con.execute(
                "UPDATE review_queue SET status = 'unmerged' WHERE source_record_id = ?",
                [source_record_id],
            )
            # Audit trail: what moved, from where to where, why, and when.
            self.con.execute(
                "INSERT INTO steward_audit VALUES ('unmerge', ?, ?, ?, ?, ?)",
                [source_record_id, old_customer_id, new_customer_id, reason, acted_at],
            )
            # Old customer loses a member (new version), new customer gets version 1.
            self.rebuild_golden([old_customer_id, new_customer_id])
            self.con.execute("COMMIT")
        except Exception:
            self.con.execute("ROLLBACK")
            raise
        return new_customer_id

    def erase_customer(self, customer_id):
        """Remove a customer's source data, crosswalk, current golden record, and history."""
        # Resolve source IDs first so associated source and review rows are removed too.
        ids = [
            r[0]
            for r in self.con.execute(
                "SELECT source_record_id FROM xref WHERE customer_id = ?", [customer_id]
            ).fetchall()
        ]
        # Tables keyed by source record: delete with an IN (?, ?, ...) list, one
        # placeholder per id. Skipped when the customer has no records.
        for t, col, vals in [
            ("source_record", "source_record_id", ids),
            ("review_queue", "source_record_id", ids),
        ]:
            if vals:
                self.con.execute(
                    f"DELETE FROM {t} WHERE {col} IN ({','.join('?' * len(vals))})",
                    vals,
                )
        # Tables keyed by customer: the crosswalk, the current master and every past version.
        # (steward_audit rows are not touched here.)
        for t in ["xref", "golden_record", "golden_history"]:
            self.con.execute(f"DELETE FROM {t} WHERE customer_id = ?", [customer_id])
        # Number of source records erased, printed by main().
        return len(ids)


def score_new_records(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Score new-versus-existing records with the saved Splink model, without retraining."""
    # A Splink backend that runs everything in an in-memory DuckDB.
    db_api = DuckDBAPI()
    # Register both standardised record sets as Splink tables, with only the model's columns.
    sdf_existing = db_api.register(existing[MODEL_COLUMNS], table_name="existing")
    sdf_new = db_api.register(new[MODEL_COLUMNS], table_name="new_records")
    # Load the trained model (comparisons, m and u values, blocking rules) from JSON.
    # The m/u values are reused as they are: no estimate_u or EM training happens here.
    linker = Linker(
        sdf_existing, str(RES / "splink_model.json"), log_level=logging.WARNING
    )
    # Term-frequency tables are required for the fields whose rarity adjusts the
    # saved model's agreement weights.
    # (Agreeing on a rare surname is stronger evidence than agreeing on "Smith".)
    for col in ["first_name_canon", "last_name", "email"]:
        linker.table_management.compute_tf_table(col)
    # predict_between compares only existing-vs-new pairs that pass the model's blocking
    # rules, and keeps pairs with probability >= REVIEW (anything lower is ignored anyway).
    preds = linker.inference.predict_between(
        sdf_existing, sdf_new, threshold_match_probability=REVIEW
    )
    # _l is the existing record, _r the new one.
    return preds.as_pandas_dataframe()[
        ["unique_id_l", "unique_id_r", "match_probability"]
    ]


def main():
    """Rebuild the demo database, demonstrate incremental MDM actions, and export tables.

    This presentation entry point intentionally deletes the prior DuckDB file first;
    use `MiniMDM` directly when testing persistence across process runs.
    """
    # Start from an empty hub each run so the demo is repeatable.
    db_path = RES / "mdm.duckdb"
    db_path.unlink(missing_ok=True)
    mdm = MiniMDM(db_path)

    # Initial data as strings (dtype=str keeps leading zeros in phones and ids).
    raw = pd.read_csv(HERE / "data/customers.csv", dtype=str)
    # Prefer the graph-repaired clusters (fewer false merges); fall back to plain Splink.
    cluster_file = RES / "clusters_graph.csv"
    if not cluster_file.exists():
        cluster_file = RES / "clusters_splink.csv"
    clusters = pd.read_csv(cluster_file)
    print("initial clusters from", cluster_file.name)
    # Seed the master from the batch clusters and report (customers, source records).
    mdm.initial_load(raw, clusters)
    print(
        "initial load:",
        mdm.con.execute(
            "SELECT count(*) customers, sum(n_source_records) records FROM golden_record"
        ).fetchone(),
    )

    # incremental batch
    # A later delivery: score it against the existing records with the saved model,
    # then attach, queue for review, or create customers.
    raw_new = pd.read_csv(HERE / "data/new_batch.csv", dtype=str)
    pairs = score_new_records(standardise(raw), standardise(raw_new))
    stats = mdm.incremental_load(raw_new, pairs)
    print("incremental batch:", stats)

    # Use synthetic truth only after matching to measure the incremental decisions;
    # it is not passed into the model or the linkage decisions.
    # truth: source_record_id -> the real person id, for old and new records.
    truth = pd.concat([raw, raw_new]).set_index("source_record_id")["true_entity_id"]
    # Current crosswalk, with the true person added next to each assignment.
    x = (
        mdm.con.execute("SELECT source_record_id, customer_id FROM xref")
        .df()
        .set_index("source_record_id")
    )
    x["true"] = truth
    # Which real person each pre-existing customer stands for: the most common true id
    # among its initial records (mode()[0] takes the first most frequent value).
    cust_truth = (
        x.loc[raw.source_record_id]
        .groupby("customer_id")["true"]
        .agg(lambda s: s.mode()[0])
    )
    # Crosswalk rows of the new batch only.
    new = x.loc[raw_new.source_record_id]
    existing_people = set(raw.true_entity_id)
    # ok_link: returning people attached to the customer that represents them.
    ok_link = sum(
        1
        for rid, r in new.iterrows()
        if r.true in existing_people and cust_truth.get(r.customer_id) == r.true
    )
    # should_link: new records whose person already existed (the recall denominator).
    should_link = sum(1 for _, r in new.iterrows() if r.true in existing_people)
    # wrong_link: new records attached to an existing customer that is someone else
    # (a false merge). Provisional new customers are not in cust_truth, so they never count.
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
    # Pick the customer with the most source records, to show erasure reaching every source row.
    victim = mdm.con.execute(
        "SELECT customer_id FROM golden_record ORDER BY n_source_records DESC LIMIT 1"
    ).fetchone()[0]
    print(f"GDPR erase {victim}: removed {mdm.erase_customer(victim)} source records")

    # exports
    # Write the main hub tables to CSV for easy inspection (06_customer_spine.py reads
    # the DuckDB file itself, not these CSVs).
    mdm.con.execute("SELECT * FROM golden_record ORDER BY customer_id").df().to_csv(
        RES / "mdm_golden_record.csv", index=False
    )
    mdm.con.execute("SELECT * FROM xref ORDER BY customer_id").df().to_csv(
        RES / "mdm_xref.csv", index=False
    )
    mdm.con.execute("SELECT * FROM review_queue").df().to_csv(
        RES / "mdm_review_queue.csv", index=False
    )
    # Show one multi-source golden record with a phone, and the provenance of its fields
    # (truncated to 600 characters to keep the console readable).
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
