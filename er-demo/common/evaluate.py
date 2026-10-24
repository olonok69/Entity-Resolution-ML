"""Match-quality metrics against the known truth (true_entity_id).

pairwise : precision / recall / F1 over all record pairs that end in the same cluster
b_cubed  : per-record precision / recall, does not over-weight big clusters

Also provides blocking_recall() (how many true pairs blocking kept) and
union_find_clusters() (turn accepted pair links into customers).

How to read the numbers:
- false_merges_pairs: pairs put together that are really different people (hurts precision).
  This is the costly error: two customers' data mixed into one profile.
- missed_pairs: pairs of the same person left apart (hurts recall): a duplicate customer.
- largest_cluster: a sudden big cluster is the classic sign of chaining (slide 15).

Used by: steps 01, 02, 03, 04, 06 and 08. Slides: 12 (Labels), 13 (Precision or recall), 15, 27.
"""

# Counter counts how many times each value occurs.
from collections import Counter
# combinations(xs, 2) yields every unordered pair from xs exactly once.
from itertools import combinations

import pandas as pd


def _pairs(groups: pd.Series) -> set[tuple]:
    """Enumerate record pairs that share a group, for pairwise metric calculations."""
    pairs = set()
    # groups maps record id (index) -> cluster label (value). groupby(groups).groups gives
    # {cluster label: index of record ids in that cluster}.
    for _, ids in groups.groupby(groups).groups.items():
        # Sort so each pair is always written (smaller id, larger id) and sets compare cleanly.
        ids = sorted(ids)
        # Pairwise metrics count every co-clustered pair, so large clusters contribute quadratically.
        pairs.update(combinations(ids, 2))
    return pairs


def evaluate_clusters(record_ids, predicted_cluster, true_entity) -> dict:
    """Compare predicted entity assignments with truth using pairwise and B-cubed metrics."""
    # One row per record: its predicted cluster and its true person, indexed by record id.
    df = pd.DataFrame(
        {"rid": record_ids, "pred": predicted_cluster, "true": true_entity}
    ).set_index("rid")
    # All pairs the matcher put together, and all pairs that really are the same person.
    pred_pairs, true_pairs = _pairs(df["pred"]), _pairs(df["true"])
    # True positives: pairs in both sets (set intersection with &).
    tp = len(pred_pairs & true_pairs)
    # Pair precision: of the pairs we merged, the share that are correct.
    p = tp / len(pred_pairs) if pred_pairs else 0.0
    # Pair recall: of the pairs that should be merged, the share we found.
    r = tp / len(true_pairs) if true_pairs else 0.0

    # B-cubed gives each record equal weight, unlike pairwise scores for large clusters.
    # Member lists per predicted cluster and per true person.
    pred_members = df.groupby("pred").groups
    true_members = df.groupby("true").groups
    bp = br = 0.0
    # For each record, compare its predicted cluster (pc) with its true cluster (tc).
    for rid, row in df.iterrows():
        pc, tc = set(pred_members[row.pred]), set(true_members[row.true])
        # Records that are correctly in the same cluster as this one (including itself).
        inter = len(pc & tc)
        # Record precision: share of my predicted cluster that is really me.
        bp += inter / len(pc)
        # Record recall: share of my real records that ended up in my cluster.
        br += inter / len(tc)
    # Average over all records.
    n = len(df)
    bp, br = bp / n, br / n

    # Histogram of cluster sizes (computed but not returned; kept for inspection).
    sizes = Counter(df["pred"].value_counts())
    return {
        "pair_precision": round(p, 4),
        "pair_recall": round(r, 4),
        # F1 is the harmonic mean of precision and recall.
        "pair_f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
        "bcubed_precision": round(bp, 4),
        "bcubed_recall": round(br, 4),
        "bcubed_f1": round(2 * bp * br / (bp + br), 4) if bp + br else 0.0,
        "n_records": n,
        # Number of customers the matcher produced versus the real number of people.
        "n_pred_entities": df["pred"].nunique(),
        "n_true_entities": df["true"].nunique(),
        # Size of the biggest predicted cluster; large values signal chaining.
        "largest_cluster": max(df["pred"].value_counts()),
        # Set difference: merged pairs that are wrong, and true pairs we never merged.
        "false_merges_pairs": len(pred_pairs - true_pairs),
        "missed_pairs": len(true_pairs - pred_pairs),
    }


def blocking_recall(candidate_pairs: set[tuple], true_entity: pd.Series) -> dict:
    """Pair completeness of the blocking step: share of true pairs that were ever compared."""
    # true_entity is indexed by record id, so _pairs gives every true same-person pair.
    true_pairs = _pairs(true_entity)
    # Put each candidate pair in (smaller, larger) order to match the format of true_pairs.
    cand = {tuple(sorted(p)) for p in candidate_pairs}
    n = len(true_entity)
    return {
        "candidate_pairs": len(cand),
        # Pair completeness: a true pair that blocking drops can never be matched later.
        "pair_completeness": round(len(cand & true_pairs) / len(true_pairs), 4),
        # Reduction ratio: share of all n*(n-1)/2 possible pairs that blocking avoided.
        "reduction_ratio": round(1 - len(cand) / (n * (n - 1) / 2), 6),
    }


def union_find_clusters(ids, pairs) -> dict:
    """Connected components over matched pairs -> {record_id: cluster_id}."""
    # Union-find (disjoint set): every record starts as its own cluster (its own parent).
    parent = {i: i for i in ids}

    def find(x):
        # Walk up to the root of x's tree; the root id names the cluster.
        while parent[x] != x:
            # Path halving: point x at its grandparent so future lookups are faster.
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # Each matched pair joins the two clusters it touches. A chain A-B, B-C puts A and C
    # together even if A-C was never matched: this is why one bad edge can chain customers.
    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            # Attach the larger root under the smaller one, so cluster ids are deterministic.
            parent[max(ra, rb)] = min(ra, rb)
    # Final lookup: every record id mapped to its cluster root.
    return {i: find(i) for i in ids}
