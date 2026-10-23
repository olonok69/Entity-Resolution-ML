"""Approach 1: deterministic rules + weighted fuzzy score (rapidfuzz) + Union-Find.

This is the "classic" hand-built matcher (same family as the CloserStill / Mars / Genus work):
  1. standardise
  2. blocking: only compare records that share a cheap key
  3. score each candidate pair with weighted fuzzy similarities
  4. two thresholds: auto-match / review queue / no-match
  5. connected components over auto-matches -> entities
"""

import sys
from itertools import combinations
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).parent))
from common.evaluate import (
    blocking_recall,
    evaluate_clusters,
    union_find_clusters,
)  # noqa: E402
from common.standardise import standardise  # noqa: E402

HERE = Path(__file__).parent
AUTO_MATCH, REVIEW = 0.80, 0.65

# Each key is a separate, inexpensive way to find plausible pairs. Their union favors
# recall: a pair missed by one key can still be proposed by another.
BLOCKING_KEYS = [
    ["email"],
    ["phone"],
    ["dob", "surname_metaphone"],
    ["postcode", "first_metaphone"],
    ["first_name_canon", "last_name"],
]


def candidate_pairs(df: pd.DataFrame) -> set[tuple]:
    """Union candidate pairs from each blocking key, skipping oversized blocks."""
    pairs = set()
    for keys in BLOCKING_KEYS:
        sub = df.dropna(subset=keys)
        for _, ids in sub.groupby(keys)["unique_id"]:
            # A block of n records creates n*(n-1)/2 comparisons. Skip very large
            # blocks (often generic/shared identifiers) to avoid a comparison explosion.
            if 1 < len(ids) <= 200:
                pairs.update(tuple(sorted(p)) for p in combinations(ids, 2))
    # A pair can share several blocking keys; the set keeps it from being scored twice.
    return pairs


def sim(a, b, fn=fuzz.ratio):
    """Return a normalized fuzzy similarity, or None when either value is missing."""
    if a is None or b is None or pd.isna(a) or pd.isna(b):
        return None
    return fn(str(a), str(b)) / 100


def score(r1, r2) -> float:
    """Score a candidate pair with weighted similarities and renormalized present fields."""
    # Names and contact fields allow fuzzy agreement; DOB, phone and postcode are exact
    # checks. These hand-chosen weights are illustrative, not learned probabilities.
    parts = {
        "first": (sim(r1.first_name_canon, r2.first_name_canon), 0.15),
        "last": (sim(r1.last_name, r2.last_name), 0.20),
        "dob": (
            (
                1.0
                if r1.dob == r2.dob
                else 0.0 if pd.notna(r1.dob) and pd.notna(r2.dob) else None
            ),
            0.20,
        ),
        "email": (sim(r1.email, r2.email), 0.20),
        "phone": (
            1.0 if r1.phone == r2.phone else 0.0 if r1.phone and r2.phone else None,
            0.15,
        ),
        "postcode": (
            (
                1.0
                if r1.postcode == r2.postcode
                else 0.0 if r1.postcode and r2.postcode else None
            ),
            0.05,
        ),
        "address": (sim(r1.address, r2.address, fuzz.token_set_ratio), 0.05),
    }
    # Missing fields contribute no evidence. Renormalising prevents records with fewer
    # populated fields from being penalized just for having less data.
    got = [(s, w) for s, w in parts.values() if s is not None]
    total_w = sum(w for _, w in got)
    return sum(s * w for s, w in got) / total_w if total_w else 0.0


def main():
    """Run the rules matcher, evaluate its clusters, and write CSV outputs."""
    raw = pd.read_csv(HERE / "data/customers.csv")
    df = standardise(raw)
    by_id = df.set_index("unique_id")

    cands = candidate_pairs(df)
    # Ground truth is used only to measure how much of the true-match set blocking retained.
    print(
        "blocking:", blocking_recall(cands, df.set_index("unique_id")["true_entity_id"])
    )

    scored = [(a, b, score(by_id.loc[a], by_id.loc[b])) for a, b in cands]
    scored = pd.DataFrame(scored, columns=["id_l", "id_r", "score"])
    # Keep the middle band for a steward; only the high-confidence band creates graph edges.
    matches = scored[scored.score >= AUTO_MATCH]
    review = scored[(scored.score >= REVIEW) & (scored.score < AUTO_MATCH)]
    print(f"auto-matches: {len(matches)}, review queue: {len(review)}")

    # Transitive closure means A-B and B-C place all three records in one entity,
    # even when A-C was never a candidate pair.
    clusters = union_find_clusters(df.unique_id, zip(matches.id_l, matches.id_r))
    df["cluster_id"] = df.unique_id.map(clusters)
    metrics = evaluate_clusters(df.unique_id, df.cluster_id, df.true_entity_id)
    print("quality:", metrics)

    out = HERE / "results"
    out.mkdir(exist_ok=True)
    df[["unique_id", "cluster_id"]].to_csv(out / "clusters_rapidfuzz.csv", index=False)
    review.to_csv(out / "review_queue_rapidfuzz.csv", index=False)
    pd.DataFrame([{"method": "rules + rapidfuzz", **metrics}]).to_csv(
        out / "metrics_rapidfuzz.csv", index=False
    )


if __name__ == "__main__":
    main()
