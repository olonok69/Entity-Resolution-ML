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
     which removes the cheapest set of edges that separates the conflicting records
  4. builds the identifier graph (records <-> emails / phones) and flags identifiers shared
     by more than one resolved person: the "generic identifier" list a steward needs
  5. evaluates before and after repair with the same metrics as every other approach

Run 02_splink.py and 03_ml_recordlinkage.py first.
"""

import sys
from itertools import combinations
from pathlib import Path

import networkx as nx
import pandas as pd
from rapidfuzz.distance import JaroWinkler

sys.path.insert(0, str(Path(__file__).parent))
from common.evaluate import evaluate_clusters  # noqa: E402
from common.standardise import standardise  # noqa: E402

HERE = Path(__file__).parent
RES = HERE / "results"
SPLINK_THRESHOLD, ML_THRESHOLD = 0.95, 0.9
FIRST_NAME_CONFLICT = 0.75  # Jaro-Winkler below this on canonical first names = different person


def dob_conflict(a, b) -> bool:
    """Both DOBs known and different, allowing for the common day/month swap."""
    if pd.isna(a) or pd.isna(b) or a == b:
        return False
    ya, ma, da = a.split("-")
    yb, mb, db = b.split("-")
    return not (ya == yb and ma == db and da == mb)


def name_conflict(r1, r2) -> bool:
    """First names clearly differ and nothing else explains it (same DOB, swapped order)."""
    f1, f2 = r1.first_name_canon, r2.first_name_canon
    if pd.isna(f1) or pd.isna(f2) or r1.first_metaphone == r2.first_metaphone:
        return False
    if pd.notna(r1.dob) and r1.dob == r2.dob:  # same DOB: a typo'd nickname, not a new person
        return False
    for a, b in ((f1, r2.last_name), (f2, r1.last_name)):  # swapped first / last name
        if pd.notna(b) and JaroWinkler.similarity(a, b) >= 0.85:
            return False
    return JaroWinkler.similarity(f1, f2) < FIRST_NAME_CONFLICT


def cannot_link(r1, r2) -> bool:
    """A hard business rule: evidence that two records belong to different people."""
    return dob_conflict(r1.dob, r2.dob) or name_conflict(r1, r2)


def build_graph(ids, edges: pd.DataFrame) -> nx.Graph:
    """Record graph: every record is a node, accepted pairs are edges weighted by probability."""
    g = nx.Graph()
    g.add_nodes_from(ids)
    for a, b, p in edges[["id_l", "id_r", "p"]].itertuples(index=False):
        g.add_edge(a, b, weight=float(p))
    return g


def repair(g: nx.Graph, df: pd.DataFrame) -> tuple[nx.Graph, dict]:
    """Split components that contain a cannot-link pair, using weighted minimum cuts."""
    g = g.copy()
    stats = {"components_checked": 0, "components_split": 0, "edges_cut": 0}
    queue = [c for c in nx.connected_components(g) if len(c) > 1]
    while queue:
        comp = queue.pop()
        stats["components_checked"] += 1
        recs = df.loc[sorted(comp)]
        conflict = next(
            (
                (a, b)
                for (a, r1), (b, r2) in combinations(recs.iterrows(), 2)
                if cannot_link(r1, r2)
            ),
            None,
        )
        if conflict is None:
            continue
        sub = g.subgraph(comp).copy()
        nx.set_edge_attributes(
            sub, {e: d["weight"] for e, d in sub.edges.items()}, "capacity"
        )
        _, (side_a, side_b) = nx.minimum_cut(sub, *conflict)
        cut = [(u, v) for u in side_a for v in sub[u] if v in side_b]
        g.remove_edges_from(cut)
        stats["components_split"] += 1
        stats["edges_cut"] += len(cut)
        # each side may still hold another conflict, so check both again
        queue += [c for c in nx.connected_components(g.subgraph(comp)) if len(c) > 1]
    return g, stats


def to_clusters(g: nx.Graph) -> dict:
    """Connected components -> {record_id: cluster_id}; cluster id is the smallest member id."""
    return {n: min(c) for c in nx.connected_components(g) for n in c}


def shared_identifiers(df: pd.DataFrame, clusters: dict) -> pd.DataFrame:
    """Identifier graph: emails and phones that point at more than one resolved person."""
    rows = []
    for field in ("email", "phone"):
        sub = df[df[field].notna()]
        for value, grp in sub.groupby(field):
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
    raw = pd.read_csv(HERE / "data/customers.csv")
    df = standardise(raw).set_index("unique_id")
    truth = df["true_entity_id"]

    splink = pd.read_csv(RES / "pairs_splink.csv")
    splink = splink[splink.match_probability >= SPLINK_THRESHOLD].rename(
        columns={"unique_id_l": "id_l", "unique_id_r": "id_r", "match_probability": "p"}
    )
    ml = pd.read_csv(RES / "pairs_ml_features.csv")
    ml = ml[ml.ml_probability >= ML_THRESHOLD].rename(columns={"ml_probability": "p"})

    results, final = [], {}
    for name, edges in [("splink", splink), ("ml", ml)]:
        g = build_graph(df.index, edges)
        before = evaluate_clusters(df.index, df.index.map(to_clusters(g)), truth)
        fixed, stats = repair(g, df)
        clusters = to_clusters(fixed)
        after = evaluate_clusters(df.index, df.index.map(clusters), truth)
        print(f"{name}: {stats}")
        for label, m in [("connected components", before), ("+ graph repair", after)]:
            print(
                f"  {label:22s} P={m['pair_precision']} R={m['pair_recall']} "
                f"B3-F1={m['bcubed_f1']} false-merge pairs={m['false_merges_pairs']}"
            )
        results.append({"method": f"{name} + graph repair", **after})
        final[name] = clusters

    shared = shared_identifiers(df, final["splink"])
    if len(shared):
        print(
            f"shared identifiers flagged: {len(shared)}, of which really shared by "
            f"different people: {int(shared.truly_shared.sum())}"
        )

    RES.mkdir(exist_ok=True)
    pd.DataFrame(results).to_csv(RES / "metrics_graph.csv", index=False)
    pd.DataFrame(
        {"unique_id": df.index, "cluster_id": df.index.map(final["splink"])}
    ).to_csv(RES / "clusters_graph.csv", index=False)
    shared.to_csv(RES / "shared_identifiers.csv", index=False)


if __name__ == "__main__":
    main()
