"""Approach 1: deterministic rules + weighted fuzzy score (rapidfuzz) + Union-Find.

This is the "classic" hand-built matcher (same family as the CloserStill / Mars / Genus work):
  1. standardise
  2. blocking: only compare records that share a cheap key
  3. score each candidate pair with weighted fuzzy similarities
  4. two thresholds: auto-match / review queue / no-match
  5. connected components over auto-matches -> entities

Input:  data/customers.csv (made by data/generate_data.py; it includes true_entity_id,
        the synthetic ground truth, which is used only for evaluation).
Output: results/clusters_rapidfuzz.csv      one row per record with its predicted cluster_id
        results/review_queue_rapidfuzz.csv  grey-zone pairs for a data steward
        results/metrics_rapidfuzz.csv       one row of quality metrics
Run:    python 01_rules_rapidfuzz.py   (from the er-demo folder)
Slides: 4 (pipeline), 7 (blocking), 8 (three ways to score a pair), 13 (precision or recall).

03_ml_recordlinkage.py imports candidate_pairs() from this file, so both matchers score
exactly the same candidate pairs.
"""

# sys and Path let the script find the shared "common" package next to it.
import sys

# combinations(ids, 2) yields every unordered pair from a list: (a, b), (a, c), (b, c).
from itertools import combinations
from pathlib import Path

import pandas as pd

# rapidfuzz.fuzz holds fast string-similarity functions. Each returns a score from 0
# (nothing in common) to 100 (identical).
from rapidfuzz import fuzz

# Put this script's folder on the import path so "common" can be imported no matter
# which folder the script is started from.
sys.path.insert(0, str(Path(__file__).parent))
# blocking_recall: how many true pairs survived blocking.
# evaluate_clusters: pairwise and B-cubed quality against the synthetic truth.
# union_find_clusters: connected components over matched pairs.
from common.evaluate import (
    blocking_recall,
    evaluate_clusters,
    union_find_clusters,
)  # noqa: E402
# standardise() cleans names, emails, phones and postcodes and adds derived keys
# (first_name_canon, surname_metaphone, first_metaphone, email_user, postcode_area).
from common.standardise import standardise  # noqa: E402

# Folder of this script; all input and output paths are built from it.
HERE = Path(__file__).parent
# Two thresholds give three bands: score >= 0.80 is an automatic match, 0.65 to 0.80
# goes to a human review queue, and anything below 0.65 is treated as no match.
AUTO_MATCH, REVIEW = 0.80, 0.65

# Each key is a separate, inexpensive way to find plausible pairs. Their union favors
# recall: a pair missed by one key can still be proposed by another.
# A key with several columns means "all of these columns must be equal".
BLOCKING_KEYS = [
    # Same cleaned email (plus-tags and Gmail dots already removed).
    ["email"],
    # Same cleaned phone number.
    ["phone"],
    # Same date of birth and a surname that sounds the same (Smith / Smyth).
    ["dob", "surname_metaphone"],
    # Same postcode and a first name that sounds the same.
    ["postcode", "first_metaphone"],
    # Same canonical first name (Bob -> robert) and same surname.
    ["first_name_canon", "last_name"],
]


def candidate_pairs(df: pd.DataFrame) -> set[tuple]:
    """Union candidate pairs from each blocking key, skipping oversized blocks."""
    # A set of (id_a, id_b) tuples; a set removes duplicates automatically.
    pairs = set()
    for keys in BLOCKING_KEYS:
        # Records with an empty key value cannot join a block for this key
        # (otherwise every record with a missing email would form one huge block).
        sub = df.dropna(subset=keys)
        # groupby(keys) splits the records into blocks that share the key value;
        # ["unique_id"] keeps only the record IDs of each block.
        for _, ids in sub.groupby(keys)["unique_id"]:
            # A block of n records creates n*(n-1)/2 comparisons. Skip very large
            # blocks (often generic/shared identifiers) to avoid a comparison explosion.
            # Blocks of size 1 have nobody to compare with, so they are skipped too.
            if 1 < len(ids) <= 200:
                # Sorting each pair makes (b, a) and (a, b) the same tuple, so the set
                # can recognise it as a duplicate.
                pairs.update(tuple(sorted(p)) for p in combinations(ids, 2))
    # A pair can share several blocking keys; the set keeps it from being scored twice.
    return pairs


def sim(a, b, fn=fuzz.ratio):
    """Return a normalized fuzzy similarity, or None when either value is missing."""
    # None (not 0.0) means "no evidence": a missing value is neither agreement nor
    # disagreement. score() drops these fields later.
    if a is None or b is None or pd.isna(a) or pd.isna(b):
        return None
    # fuzz.ratio is a normalised edit-distance (insertions and deletions) similarity
    # on 0..100; dividing by 100 puts every similarity on the same 0..1 scale.
    return fn(str(a), str(b)) / 100


def score(r1, r2) -> float:
    """Score a candidate pair with weighted similarities and renormalized present fields."""
    # Names and contact fields allow fuzzy agreement; DOB, phone and postcode are exact
    # checks. These hand-chosen weights are illustrative, not learned probabilities.
    # Each entry is (similarity or None, weight). The weights add up to 1.0.
    parts = {
        # Canonical first name, so nicknames such as Bob and Robert already agree.
        "first": (sim(r1.first_name_canon, r2.first_name_canon), 0.15),
        # Surname with a fuzzy ratio, so a typo such as Smith / Smyth still scores high.
        "last": (sim(r1.last_name, r2.last_name), 0.20),
        # DOB: 1.0 when equal, 0.0 when both are present but different,
        # None when either is missing (no evidence).
        "dob": (
            (
                1.0
                if r1.dob == r2.dob
                else 0.0 if pd.notna(r1.dob) and pd.notna(r2.dob) else None
            ),
            0.20,
        ),
        # Email with a fuzzy ratio, so a one-letter typo is only a small penalty.
        "email": (sim(r1.email, r2.email), 0.20),
        # Phone: exact agreement only. "r1.phone and r2.phone" is false when either
        # value is missing, which gives None (no evidence).
        "phone": (
            1.0 if r1.phone == r2.phone else 0.0 if r1.phone and r2.phone else None,
            0.15,
        ),
        # Postcode: exact agreement only, with a small weight because people move.
        "postcode": (
            (
                1.0
                if r1.postcode == r2.postcode
                else 0.0 if r1.postcode and r2.postcode else None
            ),
            0.05,
        ),
        # Address: token_set_ratio compares the sets of words, so word order and
        # extra words ("Flat 2") hurt less than with a plain ratio.
        "address": (sim(r1.address, r2.address, fuzz.token_set_ratio), 0.05),
    }
    # Missing fields contribute no evidence. Renormalising prevents records with fewer
    # populated fields from being penalized just for having less data.
    # Keep only the fields where both records had a value.
    got = [(s, w) for s, w in parts.values() if s is not None]
    # Sum of the weights that are actually in play for this pair.
    total_w = sum(w for _, w in got)
    # Weighted average of the present similarities, still on 0..1. If nothing could
    # be compared at all, the score is 0.0.
    return sum(s * w for s, w in got) / total_w if total_w else 0.0


def main():
    """Run the rules matcher, evaluate its clusters, and write CSV outputs."""
    # Load the raw multi-source records (CRM, WEB, BILLING) and clean them.
    raw = pd.read_csv(HERE / "data/customers.csv")
    df = standardise(raw)
    # Index by record ID so by_id.loc[a] returns record a in constant time.
    by_id = df.set_index("unique_id")

    # Step 2: blocking. Only these pairs are ever scored.
    cands = candidate_pairs(df)
    # Ground truth is used only to measure how much of the true-match set blocking retained.
    # Prints candidate_pairs, pair_completeness (blocking recall) and reduction_ratio.
    print(
        "blocking:", blocking_recall(cands, df.set_index("unique_id")["true_entity_id"])
    )

    # Step 3: score every candidate pair; each item is (id_a, id_b, score).
    scored = [(a, b, score(by_id.loc[a], by_id.loc[b])) for a, b in cands]
    # Turn the list into a table with named columns for filtering and saving.
    scored = pd.DataFrame(scored, columns=["id_l", "id_r", "score"])
    # Step 4: thresholds.
    # Keep the middle band for a steward; only the high-confidence band creates graph edges.
    matches = scored[scored.score >= AUTO_MATCH]
    review = scored[(scored.score >= REVIEW) & (scored.score < AUTO_MATCH)]
    print(f"auto-matches: {len(matches)}, review queue: {len(review)}")

    # Step 5: clustering.
    # Transitive closure means A-B and B-C place all three records in one entity,
    # even when A-C was never a candidate pair.
    # union_find_clusters returns {record_id: cluster_id}.
    clusters = union_find_clusters(df.unique_id, zip(matches.id_l, matches.id_r))
    # Attach the predicted cluster to each record.
    df["cluster_id"] = df.unique_id.map(clusters)
    # Compare predicted clusters with the synthetic truth: pair precision/recall/F1,
    # B-cubed scores, largest cluster, false-merge pairs and missed pairs.
    metrics = evaluate_clusters(df.unique_id, df.cluster_id, df.true_entity_id)
    print("quality:", metrics)

    # Save outputs. mkdir(exist_ok=True) does nothing if results/ already exists.
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    # Record-to-cluster assignment, kept for inspection (no later step reads it).
    df[["unique_id", "cluster_id"]].to_csv(out / "clusters_rapidfuzz.csv", index=False)
    # Grey-zone pairs a human would check.
    review.to_csv(out / "review_queue_rapidfuzz.csv", index=False)
    # One metrics row tagged with the method name; 09_compare.py collects these files.
    pd.DataFrame([{"method": "rules + rapidfuzz", **metrics}]).to_csv(
        out / "metrics_rapidfuzz.csv", index=False
    )


# Run main() only when the file is executed directly, not when 03 or 08 import it
# to reuse candidate_pairs().
if __name__ == "__main__":
    main()
