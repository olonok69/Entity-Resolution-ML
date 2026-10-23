"""Match-quality metrics against the known truth (true_entity_id).

pairwise : precision / recall / F1 over all record pairs that end in the same cluster
b_cubed  : per-record precision / recall, does not over-weight big clusters
"""

from collections import Counter
from itertools import combinations

import pandas as pd


def _pairs(groups: pd.Series) -> set[tuple]:
    """Enumerate record pairs that share a group, for pairwise metric calculations."""
    pairs = set()
    for _, ids in groups.groupby(groups).groups.items():
        ids = sorted(ids)
        # Pairwise metrics count every co-clustered pair, so large clusters contribute quadratically.
        pairs.update(combinations(ids, 2))
    return pairs


def evaluate_clusters(record_ids, predicted_cluster, true_entity) -> dict:
    """Compare predicted entity assignments with truth using pairwise and B-cubed metrics."""
    df = pd.DataFrame(
        {"rid": record_ids, "pred": predicted_cluster, "true": true_entity}
    ).set_index("rid")
    pred_pairs, true_pairs = _pairs(df["pred"]), _pairs(df["true"])
    tp = len(pred_pairs & true_pairs)
    p = tp / len(pred_pairs) if pred_pairs else 0.0
    r = tp / len(true_pairs) if true_pairs else 0.0

    # B-cubed gives each record equal weight, unlike pairwise scores for large clusters.
    pred_members = df.groupby("pred").groups
    true_members = df.groupby("true").groups
    bp = br = 0.0
    for rid, row in df.iterrows():
        pc, tc = set(pred_members[row.pred]), set(true_members[row.true])
        inter = len(pc & tc)
        bp += inter / len(pc)
        br += inter / len(tc)
    n = len(df)
    bp, br = bp / n, br / n

    sizes = Counter(df["pred"].value_counts())
    return {
        "pair_precision": round(p, 4),
        "pair_recall": round(r, 4),
        "pair_f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
        "bcubed_precision": round(bp, 4),
        "bcubed_recall": round(br, 4),
        "bcubed_f1": round(2 * bp * br / (bp + br), 4) if bp + br else 0.0,
        "n_records": n,
        "n_pred_entities": df["pred"].nunique(),
        "n_true_entities": df["true"].nunique(),
        "largest_cluster": max(df["pred"].value_counts()),
        "false_merges_pairs": len(pred_pairs - true_pairs),
        "missed_pairs": len(true_pairs - pred_pairs),
    }


def blocking_recall(candidate_pairs: set[tuple], true_entity: pd.Series) -> dict:
    """Pair completeness of the blocking step: share of true pairs that were ever compared."""
    true_pairs = _pairs(true_entity)
    cand = {tuple(sorted(p)) for p in candidate_pairs}
    n = len(true_entity)
    return {
        "candidate_pairs": len(cand),
        "pair_completeness": round(len(cand & true_pairs) / len(true_pairs), 4),
        "reduction_ratio": round(1 - len(cand) / (n * (n - 1) / 2), 6),
    }


def union_find_clusters(ids, pairs) -> dict:
    """Connected components over matched pairs -> {record_id: cluster_id}."""
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    return {i: find(i) for i in ids}
