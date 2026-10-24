"""Approach 5: graph-based resolution. Treat matching as a graph problem, not a list of pairs.

Pairwise models answer "do these two records match?". Customer identity is a graph question:
records are nodes, accepted matches are weighted edges, and a customer is a connected
component. A component can be wrong even when every edge looks good, because one bad edge
(a family email, a shared address) chains two people together.

This script:
  1. builds the record graph from the Splink and ML edges already scored by 02 and 03
  2. adds cannot-link constraints: two records with conflicting DOBs, or clearly different
     first names with no matching DOB, cannot be the same person, whatever the model says
  3. repairs any component that holds a cannot-link pair with a weighted minimum cut,
     which removes the cheapest set of edges that separates the conflicting records.
     Edge capacity is the evidence in bits (Splink's match weight, or the log-odds of the
     ML probability), because probabilities near 1.0 all look the same
  4. builds the identifier graph (records <-> emails / phones) and flags identifiers shared
     by more than one resolved person: the "generic identifier" list a steward needs
  5. evaluates before and after repair with the same metrics as every other approach

Inputs:
  data/customers.csv              raw records (standardised here again, same as every step)
  results/pairs_splink.csv        scored pairs from 02_splink.py (match_probability, match_weight)
  results/pairs_ml_features.csv   scored pairs from 03_ml_recordlinkage.py (ml_probability)

Outputs (in results/):
  metrics_graph.csv        quality after repair, one row per edge source (splink, ml)
  clusters_graph.csv       repaired Splink clusters: unique_id -> cluster_id (read by 05_mdm.py)
  shared_identifiers.csv   emails / phones that point at more than one resolved customer

How to run (from er-demo/):
  python 04_graph_resolution.py

Run 02_splink.py and 03_ml_recordlinkage.py first.

Slides: 14 (a customer is a connected component), 15 (why pair scores lie),
16 (cannot-link and min cut), 17 (min cut on the Jones component), 27 (results).
"""

# sys and Path are used to make the local "common" package importable.
import sys
# combinations(items, 2) yields every unordered pair once: (a, b) but never (b, a).
from itertools import combinations
from pathlib import Path

# networkx is a pure-Python graph library: nodes, edges, components, max-flow / min-cut.
import networkx as nx
import numpy as np
import pandas as pd
# Jaro-Winkler string similarity in [0, 1]; 1.0 = identical, and it rewards a shared prefix,
# which suits short strings such as first names ("jon" vs "john").
from rapidfuzz.distance import JaroWinkler

# Put er-demo/ on the import path so "common" resolves no matter where the script is run from.
sys.path.insert(0, str(Path(__file__).parent))
# evaluate_clusters: the shared scorer (pairwise and B-cubed precision / recall vs the truth).
from common.evaluate import evaluate_clusters  # noqa: E402
# standardise: the shared cleaning step (canonical names, metaphone codes, clean DOB, ...).
from common.standardise import standardise  # noqa: E402

# Folder of this script and the folder where every step writes its results.
HERE = Path(__file__).parent
RES = HERE / "results"
# Only pairs at or above these probabilities become edges. They match the cluster thresholds
# used in 02 (Splink, 0.95) and 03 (ML, 0.9), so "before repair" equals those steps' clusters.
SPLINK_THRESHOLD, ML_THRESHOLD = 0.95, 0.9
FIRST_NAME_CONFLICT = 0.75  # Jaro-Winkler below this on canonical first names = different person


def dob_conflict(a, b) -> bool:
    """Both DOBs known and different, allowing for the common day/month swap."""
    # A missing DOB is not evidence of a different person, and equal DOBs are no conflict.
    if pd.isna(a) or pd.isna(b) or a == b:
        return False
    # DOBs are "YYYY-MM-DD" strings after standardise(); split them into year, month, day.
    ya, ma, da = a.split("-")
    yb, mb, db = b.split("-")
    # Same year with month and day exchanged (03/04 vs 04/03) is a typing error, not a
    # different person, so only report a conflict when it is NOT such a swap.
    return not (ya == yb and ma == db and da == mb)


def name_conflict(r1, r2) -> bool:
    """First names clearly differ and nothing else explains it (same DOB, swapped order)."""
    # Canonical first names map nicknames to one form ("bob" -> "robert").
    f1, f2 = r1.first_name_canon, r2.first_name_canon
    # No name on one side, or names that sound the same (same metaphone code), is no conflict.
    if pd.isna(f1) or pd.isna(f2) or r1.first_metaphone == r2.first_metaphone:
        return False
    if pd.notna(r1.dob) and r1.dob == r2.dob:  # same DOB: a typo'd nickname, not a new person
        return False
    # If one record's first name looks like the other's last name, the fields were probably
    # entered in the wrong order ("Smith John"). That explains the difference.
    for a, b in ((f1, r2.last_name), (f2, r1.last_name)):  # swapped first / last name
        if pd.notna(b) and JaroWinkler.similarity(a, b) >= 0.85:
            return False
    # Nothing explains the difference: low similarity means two different people.
    return JaroWinkler.similarity(f1, f2) < FIRST_NAME_CONFLICT


def cannot_link(r1, r2) -> bool:
    """A hard business rule: evidence that two records belong to different people."""
    # Either rule is enough. These rules overrule any model score.
    return dob_conflict(r1.dob, r2.dob) or name_conflict(r1, r2)


def evidence_bits(p: float) -> float:
    """Match probability -> log-odds in bits, the strength of the evidence behind an edge.

    Probabilities saturate: 0.99999 and 0.999999999 both look like 1.0, yet the second edge
    has ten more bits of evidence. Cutting on bits keeps strong edges and removes weak ones.
    """
    # Clamp endpoints so log-odds stay finite; a small positive capacity also keeps
    # a zero/negative-evidence edge eligible for a minimum cut.
    p = min(max(p, 1e-12), 1 - 1e-12)
    # log2(p / (1 - p)) is the same scale as Splink's match_weight, so both edge sources
    # can be repaired with one algorithm. The floor of 0.01 bits keeps capacities positive.
    return max(float(np.log2(p / (1 - p))), 0.01)


def build_graph(ids, edges: pd.DataFrame) -> nx.Graph:
    """Record graph: every record is a node, accepted pairs are edges weighted by evidence bits."""
    # An undirected graph: a match between a and b is the same as between b and a.
    g = nx.Graph()
    # Add every record first, so records with no accepted match still exist as
    # one-node components (singleton customers).
    g.add_nodes_from(ids)
    # itertuples(index=False) yields plain (id_l, id_r, bits) tuples, faster than iterrows.
    for a, b, w in edges[["id_l", "id_r", "bits"]].itertuples(index=False):
        g.add_edge(a, b, weight=float(w))
    return g


def repair(g: nx.Graph, df: pd.DataFrame) -> tuple[nx.Graph, dict]:
    """Split components that contain a cannot-link pair, using weighted minimum cuts."""
    # Work on a copy so the caller keeps the unrepaired graph for the "before" metrics.
    g = g.copy()
    # Counters printed at the end (slide 16: 42 components split, 80 edges cut for Splink).
    stats = {"components_checked": 0, "components_split": 0, "edges_cut": 0}
    # connected_components yields one set of node ids per component. Singletons cannot hold
    # a conflicting pair, so only multi-record components go on the work queue.
    queue = [c for c in nx.connected_components(g) if len(c) > 1]
    while queue:
        comp = queue.pop()
        stats["components_checked"] += 1
        # The standardised rows of this component's records (df is indexed by unique_id).
        recs = df.loc[sorted(comp)]
        # Inspect pairs inside this component, not across already separate customers.
        # Repair one violation at a time because a cut can expose other conflicts.
        # next(generator, None) returns the first conflicting pair, or None if there is none.
        # iterrows() yields (record id, row) and combinations() makes every pair of those.
        conflict = next(
            (
                (a, b)
                for (a, r1), (b, r2) in combinations(recs.iterrows(), 2)
                if cannot_link(r1, r2)
            ),
            None,
        )
        # A component with no conflict is accepted as one customer.
        if conflict is None:
            continue
        # Copy just this component, so the cut is computed on a small graph.
        sub = g.subgraph(comp).copy()
        # nx.minimum_cut reads the edge attribute "capacity"; copy each edge's weight (bits) into it.
        nx.set_edge_attributes(
            sub, {e: d["weight"] for e, d in sub.edges.items()}, "capacity"
        )
        # Capacities represent evidence strength: a minimum cut prefers removing weaker
        # edges while preserving the stronger links that connect each side internally.
        # minimum_cut(graph, source, target) returns (cut value, (nodes on source side,
        # nodes on target side)). Only the two node sets are needed here.
        _, (side_a, side_b) = nx.minimum_cut(sub, *conflict)
        # The cut edges are exactly the edges with one end on each side.
        cut = [(u, v) for u in side_a for v in sub[u] if v in side_b]
        # Remove them from the full graph, which splits the component in two.
        g.remove_edges_from(cut)
        stats["components_split"] += 1
        stats["edges_cut"] += len(cut)
        # each side may still hold another conflict, so check both again
        queue += [c for c in nx.connected_components(g.subgraph(comp)) if len(c) > 1]
    return g, stats


def to_clusters(g: nx.Graph) -> dict:
    """Connected components -> {record_id: cluster_id}; cluster id is the smallest member id."""
    # Using the smallest member id makes the label deterministic from run to run.
    return {n: min(c) for c in nx.connected_components(g) for n in c}


def shared_identifiers(df: pd.DataFrame, clusters: dict) -> pd.DataFrame:
    """Identifier graph: emails and phones that point at more than one resolved person."""
    rows = []
    for field in ("email", "phone"):
        # Only records that actually carry this identifier.
        sub = df[df[field].notna()]
        # groupby(field) gives one group of records per distinct email (or phone) value.
        # Conceptually each value is an identifier node linked to the records in its group.
        for value, grp in sub.groupby(field):
            # Count distinct resolved entities, rather than rows: repeated records
            # inside one entity do not make an identifier "shared" across customers.
            people = {clusters[i] for i in grp.index}
            if len(people) > 1:
                rows.append(
                    {
                        "identifier_type": field,
                        "identifier": value,
                        "n_records": len(grp),
                        "n_resolved_people": len(people),
                        # truth, for evaluation only: is it really shared by different people?
                        "truly_shared": grp.true_entity_id.nunique() > 1,
                    }
                )
    return pd.DataFrame(rows)


def main():
    """Build, repair and evaluate the record graph for Splink and ML edges."""
    # Re-standardise the raw records so the cannot-link rules see canonical names,
    # metaphone codes and clean DOBs. Index by unique_id for fast lookups by record id.
    raw = pd.read_csv(HERE / "data/customers.csv")
    df = standardise(raw).set_index("unique_id")
    # The synthetic answer key, used only to measure quality, never to decide edges.
    truth = df["true_entity_id"]

    # Splink edges: keep accepted pairs and rename columns to the names build_graph expects.
    # Splink's match_weight is already the log2 Bayes factor, i.e. evidence in bits.
    splink = pd.read_csv(RES / "pairs_splink.csv")
    splink = splink[splink.match_probability >= SPLINK_THRESHOLD].rename(
        columns={"unique_id_l": "id_l", "unique_id_r": "id_r", "match_weight": "bits"}
    )
    # ML edges: the classifier only gives a probability, so convert it to bits with
    # evidence_bits(). Series.map applies the function to every value.
    ml = pd.read_csv(RES / "pairs_ml_features.csv")
    ml = ml[ml.ml_probability >= ML_THRESHOLD]
    ml = ml.assign(bits=ml.ml_probability.map(evidence_bits))

    # results: metrics rows for the CSV; final: repaired clusters per edge source.
    results, final = [], {}
    for name, edges in [("splink", splink), ("ml", ml)]:
        g = build_graph(df.index, edges)
        # "Before": plain connected components (transitive closure), as in 02 and 03.
        # df.index.map(dict) looks up each record's cluster id in the dictionary.
        before = evaluate_clusters(df.index, df.index.map(to_clusters(g)), truth)
        # "After": the same graph once cannot-link conflicts are cut apart.
        fixed, stats = repair(g, df)
        clusters = to_clusters(fixed)
        after = evaluate_clusters(df.index, df.index.map(clusters), truth)
        print(f"{name}: {stats}")
        # {label:22s} pads the label to 22 characters so the two lines align.
        for label, m in [("connected components", before), ("+ graph repair", after)]:
            print(
                f"  {label:22s} P={m['pair_precision']} R={m['pair_recall']} "
                f"B3-F1={m['bcubed_f1']} false-merge pairs={m['false_merges_pairs']}"
            )
        # **after unpacks the metrics dict into the row next to the method name.
        results.append({"method": f"{name} + graph repair", **after})
        final[name] = clusters

    # The identifier view is built on the repaired Splink clusters, the ones MDM uses next.
    shared = shared_identifiers(df, final["splink"])
    if len(shared):
        print(
            f"shared identifiers flagged: {len(shared)}, of which really shared by "
            f"different people: {int(shared.truly_shared.sum())}"
        )

    # Write outputs: metrics for 09_compare.py, repaired Splink clusters for 05_mdm.py,
    # and the shared-identifier list as a steward work queue.
    RES.mkdir(exist_ok=True)
    pd.DataFrame(results).to_csv(RES / "metrics_graph.csv", index=False)
    pd.DataFrame(
        {"unique_id": df.index, "cluster_id": df.index.map(final["splink"])}
    ).to_csv(RES / "clusters_graph.csv", index=False)
    shared.to_csv(RES / "shared_identifiers.csv", index=False)


# Run main() only when the file is executed directly, not when it is imported.
if __name__ == "__main__":
    main()
