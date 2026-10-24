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

Inputs:
    results/mdm.duckdb          tables golden_record, xref, source_record (from 05_mdm.py)
    results/splink_model.json   hashed to stamp the match model version on every spine row
    data/customers.csv, data/new_batch.csv   generator truth, used only to evaluate households

Outputs:
    new DuckDB tables household, identity_hierarchy, customer_spine, column_classification
    results/customer_spine.csv, identity_hierarchy.csv, spine_contracts.csv,
    metrics_households.csv

How to run:
    python 06_customer_spine.py      (after 02_splink.py and 05_mdm.py)

Related slides: 19 (mini MDM), 20 (customer spine and hierarchy), 25 (lakehouse mapping).
"""

# hashlib fingerprints the match model file, so each spine row records which model built it.
import hashlib
import sys
# Timezone-aware UTC timestamps for valid_from / published_at lineage columns.
from datetime import datetime, timezone
from pathlib import Path

# DuckDB is the embedded SQL database that the MDM hub (step 5) already wrote to.
import duckdb
# networkx gives us a graph and its connected components, used to find households.
import networkx as nx
import pandas as pd
# rapidfuzz compares address strings that are spelled slightly differently.
from rapidfuzz import fuzz

# Make the local "common" package importable when the script is run from any folder.
sys.path.insert(0, str(Path(__file__).parent))
# evaluate_clusters compares predicted groups to true groups (pairwise and B-cubed metrics).
from common.evaluate import evaluate_clusters  # noqa: E402

# Paths are relative to this file so the script works from any working directory.
HERE = Path(__file__).parent
RES = HERE / "results"
# fuzz.token_set_ratio returns 0-100. It ignores word order and duplicated words, so
# "12 High St Flat 2" and "Flat 2, 12 High St" score 100. 85 tolerates small typos.
ADDRESS_SIMILARITY = 85  # token-set ratio for "same address" inside a postcode

# Governance metadata: every personal column in the spine gets a privacy class.
# A data contract below checks that none of them is left unclassified.
PII_COLUMNS = {
    "first_name": "PII",
    "last_name": "PII",
    "dob": "PII_SENSITIVE",  # date of birth is a strong identifier, so it is ranked higher
    "email": "PII",
    "phone": "PII",
    "address": "PII",
    "city": "PII_LOW",  # coarse location, low risk on its own
    "postcode": "PII_LOW",
}


def households(golden: pd.DataFrame, members: pd.DataFrame) -> pd.DataFrame:
    """Households as a graph: customers are linked through the addresses of their records.

    Every source record contributes an address node (postcode + fuzzy-matched street line),
    so a person whose golden address is a newer one still links to the home they share.
    Connected components of the customer-address graph are households.
    """
    # Undirected graph with two kinds of nodes: customer ids (strings) and address
    # nodes (tuples). A customer is joined to every address seen on any of its records.
    g = nx.Graph()
    # Add every customer first, so people with no usable address still form their own
    # one-person component (a single_person household) instead of vanishing.
    g.add_nodes_from(golden.customer_id)
    # An address on any source record can connect customers, even if survivorship
    # selected a newer address for one of their golden records.
    # Keep only records that have both a postcode and a street, then process one postcode
    # at a time (groupby yields the postcode value and the rows that share it).
    for pc, grp in members[members.postcode.notna() & members.address.notna()].groupby(
        "postcode"
    ):
        # Compare street strings only within the same postcode to limit false joins
        # and keep the address grouping work manageable.
        streets: list[str] = []  # one representative per distinct address in this postcode
        # Walk the records of this postcode with their customer id and lower-cased street.
        for cid, addr in zip(grp.customer_id, grp.address.str.lower()):
            # next() returns the first known street that is similar enough, or None.
            # This is a greedy "leader" clustering of addresses: the first spelling seen
            # becomes the representative that later spellings are compared to.
            node = next(
                (s for s in streets if fuzz.token_set_ratio(addr, s) >= ADDRESS_SIMILARITY),
                None,
            )
            # No similar street yet: this spelling becomes a new address representative.
            if node is None:
                streets.append(addr)
                node = addr
            # The address tuple is a shared graph node; customers connected through
            # it end up in the same household component.
            g.add_edge(cid, ("ADDR", pc, node))
    # Lookup customer_id -> lower-cased surname, used to label the household rule.
    surname = dict(zip(golden.customer_id, golden.last_name.str.lower()))
    rows = []
    # Each connected component is one household: everyone reachable through shared addresses.
    for comp in nx.connected_components(g):
        # Address nodes are tuples, while customer IDs are strings; ignore address
        # nodes when assigning household membership and calculating household size.
        people = sorted(n for n in comp if isinstance(n, str))
        if not people:
            continue
        # Explain why the household exists (the rule is stored on the hierarchy edge):
        # one person, everyone shares a surname (likely a family), or only the address.
        rule = (
            "single_person"
            if len(people) == 1
            else "same_address_same_surname"
            if len({surname[c] for c in people}) == 1
            else "same_address"
        )
        # Deterministic household id: reuse the digits of the smallest customer id,
        # so "C0000042" becomes "H0000042". Same members give the same id on every build.
        hid = "H" + people[0][1:]
        # One output row per member customer of this household.
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
    # Level 1: households. They have no parent and no confidence score.
    nodes = [
        {"node_id": h, "node_type": "HOUSEHOLD", "parent_id": None, "rule": "root", "confidence": None}
        for h in hh.household_id.unique()
    ]
    # Level 2: customers. The edge rule is the household rule; it is deterministic,
    # so there is no probability to store.
    nodes += [
        {"node_id": c, "node_type": "CUSTOMER", "parent_id": h, "rule": r, "confidence": None}
        for c, h, r in zip(hh.customer_id, hh.household_id, hh.rule)
    ]
    # Level 3: source records. The edge carries how the MDM linked the record
    # (match_method, e.g. splink_batch_cluster or steward_approved) and the match probability.
    nodes += [
        {"node_id": s, "node_type": "SOURCE", "parent_id": c, "rule": m, "confidence": p}
        for s, c, m, p in zip(
            xref.source_record_id, xref.customer_id, xref.match_method, xref.match_probability
        )
    ]
    # valid_from timestamps the build, so a later build can be compared to this one.
    return pd.DataFrame(nodes).assign(valid_from=ts)


def contracts(con) -> pd.DataFrame:
    """Data contracts on the spine. Each query returns the number of violations."""
    # Each entry maps a human-readable rule to a SQL query that counts the rows that
    # break it. Writing governance as executable checks means it runs on every build.
    checks = {
        # Crosswalk integrity: a source record mapped to two customers is an ambiguous identity.
        "every source record has exactly one customer": """
            SELECT count(*) FROM (SELECT source_record_id FROM xref GROUP BY 1 HAVING count(*) <> 1)""",
        # No orphans: an anti-join (LEFT JOIN ... IS NULL) finds records missing from the crosswalk.
        "no source record without a crosswalk entry": """
            SELECT count(*) FROM source_record s LEFT JOIN xref x USING (source_record_id)
            WHERE x.customer_id IS NULL""",
        # A customer id used in the crosswalk must have a golden record to join to.
        "every live customer has a golden record": """
            SELECT count(DISTINCT x.customer_id) FROM xref x
            LEFT JOIN golden_record g USING (customer_id) WHERE g.customer_id IS NULL""",
        # Hierarchy shape: a customer appears once, so it has exactly one parent household.
        "every customer belongs to exactly one household": """
            SELECT count(*) FROM (SELECT node_id FROM identity_hierarchy
            WHERE node_type = 'CUSTOMER' GROUP BY 1 HAVING count(*) <> 1)""",
        # Referential integrity inside the hierarchy: the parent household node must exist.
        "every customer's household exists": """
            SELECT count(*) FROM identity_hierarchy c LEFT JOIN identity_hierarchy h
            ON h.node_id = c.parent_id AND h.node_type = 'HOUSEHOLD'
            WHERE c.node_type = 'CUSTOMER' AND h.node_id IS NULL""",
        # The spine key is what every downstream table joins on, so it must be unique.
        "spine key is unique": """
            SELECT count(*) - count(DISTINCT customer_id) FROM customer_spine""",
        # Expected number of classified columns minus the number actually classified.
        "every PII column is classified": f"""
            SELECT {len(PII_COLUMNS)} - count(*) FROM column_classification
            WHERE table_name = 'customer_spine'""",
    }
    rows = []
    for name, sql in checks.items():
        # Each contract query returns a violation count; zero is the only passing result.
        # fetchone()[0] takes the single number from the single result row.
        n = con.execute(sql).fetchone()[0]
        rows.append({"contract": name, "violations": int(n), "passed": n == 0})
    return pd.DataFrame(rows)


def main():
    """Build households, hierarchy and spine on top of the MDM, check contracts, publish."""
    # Open the MDM database written by 05_mdm.py; new tables are added next to its tables.
    db = RES / "mdm.duckdb"
    con = duckdb.connect(str(db))
    # One publish timestamp for the whole build, stored as lineage on every row.
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # The match model version is the first 12 hex characters of the SHA-256 of the Splink
    # model JSON. Any change to the model gives a new version, so consumers can tell
    # which model produced a customer.
    model_file = RES / "splink_model.json"
    model_version = hashlib.sha256(model_file.read_bytes()).hexdigest()[:12]

    # Load the MDM tables into pandas. .df() turns a DuckDB result into a DataFrame.
    golden = con.execute("SELECT * FROM golden_record").df()
    xref = con.execute("SELECT * FROM xref").df()
    # Every source record's address, tagged with the customer it was resolved to.
    # Using all records (not only the golden address) lets old shared addresses link people.
    members = con.execute(
        "SELECT x.customer_id, s.address, s.postcode FROM xref x JOIN source_record s USING (source_record_id)"
    ).df()
    # Level above the customer: group customers into households.
    hh = households(golden, members)
    # One parent-child table for HOUSEHOLD -> CUSTOMER -> SOURCE.
    hier = build_hierarchy(xref, hh, ts)

    # register() exposes a pandas DataFrame to DuckDB SQL under a view name, so it can
    # be materialised as a real table with CREATE OR REPLACE (rebuilt on every run).
    con.register("hh", hh)
    con.register("hier", hier)
    con.execute("CREATE OR REPLACE TABLE household AS SELECT * FROM hh")
    con.execute("CREATE OR REPLACE TABLE identity_hierarchy AS SELECT * FROM hier")
    # The spine is a consumer-facing projection: one row per golden customer, with
    # source keys and lineage metadata alongside mastered attributes.
    # list(... ORDER BY ...) aggregates every source key into one array, for example
    # ['CRM:CRM-000123', 'WEB:WEB-000456']. min(match_probability) is the weakest link:
    # the least certain record in the customer, a quick signal for stewards.
    # GROUP BY ALL groups by every non-aggregated column, giving one row per customer.
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
    # Column classification table: one row per PII column of the spine and its class.
    # Catalogs such as Unity Catalog store the same information as column tags.
    classification = pd.DataFrame(
        [
            {"table_name": "customer_spine", "column_name": c, "classification": k}
            for c, k in PII_COLUMNS.items()
        ]
    )
    con.register("cls", classification)
    con.execute("CREATE OR REPLACE TABLE column_classification AS SELECT * FROM cls")

    # Run the data contracts against the tables just built and show the result table.
    checks = contracts(con)
    print(checks.to_string(index=False))
    # Stop before exporting the spine artifacts if any required relationship or
    # classification is broken, so the failure is visible to the caller.
    # SystemExit with a message exits with a non-zero code, which fails a scheduled job.
    if not checks.passed.all():
        raise SystemExit("data contract failed: spine not published")

    # Evaluation only: use generator truth to assess household grouping, never to build it.
    # Truth for both the initial data and the new batch, indexed by source record id.
    truth = pd.concat(
        [
            pd.read_csv(HERE / "data/customers.csv", dtype=str),
            pd.read_csv(HERE / "data/new_batch.csv", dtype=str),
        ]
    ).set_index("source_record_id")
    # Evaluate at the level of true people, not records: for every record attach its
    # true person, true household and predicted household (through its customer).
    # Then collapse to one row per true person. If the MDM split a person into two
    # customers in different households, s.mode()[0] picks the most common prediction.
    ev = xref.assign(
        person=xref.source_record_id.map(truth.true_entity_id),
        true_hh=xref.source_record_id.map(truth.true_household_id),
        pred_hh=xref.customer_id.map(hh.set_index("customer_id").household_id),
    ).groupby("person").agg(true_hh=("true_hh", "first"), pred_hh=("pred_hh", lambda s: s.mode()[0]))
    # Pairwise precision: of the people we put in one household, how many truly live
    # together. Recall: of the true co-resident pairs, how many we grouped.
    m = evaluate_clusters(ev.index, ev.pred_hh, ev.true_hh)
    # len(hh) is the number of customers (one row each); multi-person households are
    # the distinct household ids with more than one member.
    print(
        f"customers: {len(hh)}, multi-person households: "
        f"{hh[hh.household_size > 1].household_id.nunique()}, people-in-household pair "
        f"precision={m['pair_precision']} recall={m['pair_recall']}"
    )
    # Node counts per hierarchy level, plus the model fingerprint stamped on the spine.
    print(
        "hierarchy nodes:",
        hier.node_type.value_counts().to_dict(),
        "| match model version:",
        model_version,
    )

    # Publish: export the spine and its companions as CSV for 09_compare.py and for review.
    con.execute("SELECT * FROM customer_spine ORDER BY customer_id").df().to_csv(
        RES / "customer_spine.csv", index=False
    )
    hier.to_csv(RES / "identity_hierarchy.csv", index=False)
    checks.to_csv(RES / "spine_contracts.csv", index=False)
    # One-row metrics table; **m unpacks the metric dict into columns.
    pd.DataFrame(
        [{"method": "households (same address)", **m}]
    ).to_csv(RES / "metrics_households.csv", index=False)
    con.close()


# Run main() only when executed as a script, not when imported by another module.
if __name__ == "__main__":
    main()
