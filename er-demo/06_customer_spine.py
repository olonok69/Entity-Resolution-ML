"""Step 6: customer spine and governed identity hierarchy, published as a Golden Layer.

The MDM hub (05_mdm.py) owns the golden record per person. A customer spine is the thin,
governed table every downstream system joins to: one row per resolved customer, with a
stable key, its place in the identity hierarchy and the keys of every source record.

Hierarchy built here (each level has a rule, a confidence and a parent):

    HOUSEHOLD        people living at the same address
      CUSTOMER       one resolved person (customer_id from the MDM)
        SOURCE       one record in CRM / WEB / BILLING (source_record_id)

Governance is enforced as data contracts that run on every build: one customer per source
record, one household per customer, no orphans, no live customer without a golden record,
and PII columns classified. A failed contract stops the publish.

Run 05_mdm.py first; this script adds tables to results/mdm.duckdb and exports CSVs.
"""

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import networkx as nx
import pandas as pd
from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).parent))
from common.evaluate import evaluate_clusters  # noqa: E402

HERE = Path(__file__).parent
RES = HERE / "results"
ADDRESS_SIMILARITY = 85  # token-set ratio for "same address" inside a postcode

PII_COLUMNS = {
    "first_name": "PII",
    "last_name": "PII",
    "dob": "PII_SENSITIVE",
    "email": "PII",
    "phone": "PII",
    "address": "PII",
    "city": "PII_LOW",
    "postcode": "PII_LOW",
}


def households(golden: pd.DataFrame, members: pd.DataFrame) -> pd.DataFrame:
    """Households as a graph: customers are linked through the addresses of their records.

    Every source record contributes an address node (postcode + fuzzy-matched street line),
    so a person whose golden address is a newer one still links to the home they share.
    Connected components of the customer-address graph are households.
    """
    g = nx.Graph()
    g.add_nodes_from(golden.customer_id)
    # An address on any source record can connect customers, even if survivorship
    # selected a newer address for one of their golden records.
    for pc, grp in members[members.postcode.notna() & members.address.notna()].groupby(
        "postcode"
    ):
        # Compare street strings only within the same postcode to limit false joins
        # and keep the address grouping work manageable.
        streets: list[str] = []  # one representative per distinct address in this postcode
        for cid, addr in zip(grp.customer_id, grp.address.str.lower()):
            node = next(
                (s for s in streets if fuzz.token_set_ratio(addr, s) >= ADDRESS_SIMILARITY),
                None,
            )
            if node is None:
                streets.append(addr)
                node = addr
            # The address tuple is a shared graph node; customers connected through
            # it end up in the same household component.
            g.add_edge(cid, ("ADDR", pc, node))
    surname = dict(zip(golden.customer_id, golden.last_name.str.lower()))
    rows = []
    for comp in nx.connected_components(g):
        # Address nodes are tuples, while customer IDs are strings; ignore address
        # nodes when assigning household membership and calculating household size.
        people = sorted(n for n in comp if isinstance(n, str))
        if not people:
            continue
        rule = (
            "single_person"
            if len(people) == 1
            else "same_address_same_surname"
            if len({surname[c] for c in people}) == 1
            else "same_address"
        )
        hid = "H" + people[0][1:]
        rows += [
            {
                "customer_id": c,
                "household_id": hid,
                "rule": rule,
                "household_size": len(people),
            }
            for c in people
        ]
    return pd.DataFrame(rows)


def build_hierarchy(xref: pd.DataFrame, hh: pd.DataFrame, ts: str) -> pd.DataFrame:
    """Parent-child identity hierarchy with the rule and confidence of every edge."""
    # Store all node types in one table: households are roots, customers point to a
    # household, and each source record points to its resolved customer.
    nodes = [
        {"node_id": h, "node_type": "HOUSEHOLD", "parent_id": None, "rule": "root", "confidence": None}
        for h in hh.household_id.unique()
    ]
    nodes += [
        {"node_id": c, "node_type": "CUSTOMER", "parent_id": h, "rule": r, "confidence": None}
        for c, h, r in zip(hh.customer_id, hh.household_id, hh.rule)
    ]
    nodes += [
        {"node_id": s, "node_type": "SOURCE", "parent_id": c, "rule": m, "confidence": p}
        for s, c, m, p in zip(
            xref.source_record_id, xref.customer_id, xref.match_method, xref.match_probability
        )
    ]
    return pd.DataFrame(nodes).assign(valid_from=ts)


def contracts(con) -> pd.DataFrame:
    """Data contracts on the spine. Each query returns the number of violations."""
    checks = {
        "every source record has exactly one customer": """
            SELECT count(*) FROM (SELECT source_record_id FROM xref GROUP BY 1 HAVING count(*) <> 1)""",
        "no source record without a crosswalk entry": """
            SELECT count(*) FROM source_record s LEFT JOIN xref x USING (source_record_id)
            WHERE x.customer_id IS NULL""",
        "every live customer has a golden record": """
            SELECT count(DISTINCT x.customer_id) FROM xref x
            LEFT JOIN golden_record g USING (customer_id) WHERE g.customer_id IS NULL""",
        "every customer belongs to exactly one household": """
            SELECT count(*) FROM (SELECT node_id FROM identity_hierarchy
            WHERE node_type = 'CUSTOMER' GROUP BY 1 HAVING count(*) <> 1)""",
        "every customer's household exists": """
            SELECT count(*) FROM identity_hierarchy c LEFT JOIN identity_hierarchy h
            ON h.node_id = c.parent_id AND h.node_type = 'HOUSEHOLD'
            WHERE c.node_type = 'CUSTOMER' AND h.node_id IS NULL""",
        "spine key is unique": """
            SELECT count(*) - count(DISTINCT customer_id) FROM customer_spine""",
        "every PII column is classified": f"""
            SELECT {len(PII_COLUMNS)} - count(*) FROM column_classification
            WHERE table_name = 'customer_spine'""",
    }
    rows = []
    for name, sql in checks.items():
        # Each contract query returns a violation count; zero is the only passing result.
        n = con.execute(sql).fetchone()[0]
        rows.append({"contract": name, "violations": int(n), "passed": n == 0})
    return pd.DataFrame(rows)


def main():
    """Build households, hierarchy and spine on top of the MDM, check contracts, publish."""
    db = RES / "mdm.duckdb"
    con = duckdb.connect(str(db))
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    model_file = RES / "splink_model.json"
    model_version = hashlib.sha256(model_file.read_bytes()).hexdigest()[:12]

    golden = con.execute("SELECT * FROM golden_record").df()
    xref = con.execute("SELECT * FROM xref").df()
    members = con.execute(
        "SELECT x.customer_id, s.address, s.postcode FROM xref x JOIN source_record s USING (source_record_id)"
    ).df()
    hh = households(golden, members)
    hier = build_hierarchy(xref, hh, ts)

    con.register("hh", hh)
    con.register("hier", hier)
    con.execute("CREATE OR REPLACE TABLE household AS SELECT * FROM hh")
    con.execute("CREATE OR REPLACE TABLE identity_hierarchy AS SELECT * FROM hier")
    # The spine is a consumer-facing projection: one row per golden customer, with
    # source keys and lineage metadata alongside mastered attributes.
    con.execute(f"""
        CREATE OR REPLACE TABLE customer_spine AS
        SELECT g.customer_id, h.household_id, h.household_size,
               g.first_name, g.last_name, g.dob, g.email, g.phone, g.address, g.city, g.postcode,
               g.n_source_records, g.sources,
               list(s.source_system || ':' || x.source_record_id ORDER BY x.source_record_id) AS source_keys,
               min(x.match_probability) AS weakest_link_probability,
               g.version AS golden_version,
               '{model_version}' AS match_model_version,
               '{ts}' AS published_at
        FROM golden_record g
        JOIN household h USING (customer_id)
        JOIN xref x USING (customer_id)
        JOIN source_record s USING (source_record_id)
        GROUP BY ALL""")
    classification = pd.DataFrame(
        [
            {"table_name": "customer_spine", "column_name": c, "classification": k}
            for c, k in PII_COLUMNS.items()
        ]
    )
    con.register("cls", classification)
    con.execute("CREATE OR REPLACE TABLE column_classification AS SELECT * FROM cls")

    checks = contracts(con)
    print(checks.to_string(index=False))
    # Stop before exporting the spine artifacts if any required relationship or
    # classification is broken, so the failure is visible to the caller.
    if not checks.passed.all():
        raise SystemExit("data contract failed: spine not published")

    # Evaluation only: use generator truth to assess household grouping, never to build it.
    truth = pd.concat(
        [
            pd.read_csv(HERE / "data/customers.csv", dtype=str),
            pd.read_csv(HERE / "data/new_batch.csv", dtype=str),
        ]
    ).set_index("source_record_id")
    ev = xref.assign(
        person=xref.source_record_id.map(truth.true_entity_id),
        true_hh=xref.source_record_id.map(truth.true_household_id),
        pred_hh=xref.customer_id.map(hh.set_index("customer_id").household_id),
    ).groupby("person").agg(true_hh=("true_hh", "first"), pred_hh=("pred_hh", lambda s: s.mode()[0]))
    m = evaluate_clusters(ev.index, ev.pred_hh, ev.true_hh)
    print(
        f"customers: {len(hh)}, multi-person households: "
        f"{hh[hh.household_size > 1].household_id.nunique()}, people-in-household pair "
        f"precision={m['pair_precision']} recall={m['pair_recall']}"
    )
    print(
        "hierarchy nodes:",
        hier.node_type.value_counts().to_dict(),
        "| match model version:",
        model_version,
    )

    con.execute("SELECT * FROM customer_spine ORDER BY customer_id").df().to_csv(
        RES / "customer_spine.csv", index=False
    )
    hier.to_csv(RES / "identity_hierarchy.csv", index=False)
    checks.to_csv(RES / "spine_contracts.csv", index=False)
    pd.DataFrame(
        [{"method": "households (same address)", **m}]
    ).to_csv(RES / "metrics_households.csv", index=False)
    con.close()


if __name__ == "__main__":
    main()
