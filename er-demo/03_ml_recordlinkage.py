"""Approach 3: supervised ML matcher with the `recordlinkage` toolkit + scikit-learn.

"ML where rules fall short": when you have labelled pairs (from data stewards reviewing the
grey zone), train a classifier on pair features. Here labels come from the synthetic truth.

- indexing: same blocking keys as approach 1 (recordlinkage.Index also has block / sortedneighbourhood)
- features: string similarities (Jaro-Winkler, Levenshtein, q-gram), exact matches, date and
  phonetic agreement, plus a char-n-gram TF-IDF cosine of the whole record (cheap "embedding")
- model: gradient boosting, 2-fold cross-fitting by the left record's entity. This is
  out-of-fold scoring, but is not a strict entity-disjoint split; step 8 shows that version.

Input:  data/customers.csv
Output: results/pairs_ml_features.csv  one row per candidate pair: 14 features, label and
                                       out-of-fold ml_probability (used by 04_graph_resolution.py)
        results/metrics_ml.csv         one row of quality metrics
Run:    python 03_ml_recordlinkage.py   (from the er-demo folder)
Slides: 8 (three ways to score), 11 (supervised features), 12 (labels), 13 (precision or recall).

08_mlops_feature_store.py imports features() from this file, so training and serving
compute features with the same code.
"""

# sys and Path let the script find the shared "common" package next to it.
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# recordlinkage: a toolkit for record linkage; here only its Compare class is used,
# which computes one similarity column per field comparison.
import recordlinkage as rl

# Gradient-boosted decision trees; "Hist" bins numeric features for speed and handles
# NaN (missing) values natively, so missing fields need no imputation.
from sklearn.ensemble import HistGradientBoostingClassifier

# Turns text into sparse TF-IDF vectors (weighted counts of character n-grams).
from sklearn.feature_extraction.text import TfidfVectorizer

# Average precision: area under the precision-recall curve, a threshold-free ranking score.
from sklearn.metrics import average_precision_score

# Make "common" importable no matter which folder the script is started from.
sys.path.insert(0, str(Path(__file__).parent))
from common.evaluate import evaluate_clusters, union_find_clusters  # noqa: E402
from common.standardise import standardise  # noqa: E402

# A module name that starts with a digit cannot be used in an "import" statement,
# so __import__ loads 01_rules_rapidfuzz.py by its string name.
rules = __import__("01_rules_rapidfuzz")  # reuse the blocking from approach 1

HERE = Path(__file__).parent
# Pairs with predicted probability >= 0.9 become match edges.
THRESHOLD = 0.9


def record_text(df: pd.DataFrame) -> pd.Series:
    """One string per record for the whole-record TF-IDF feature."""
    # Join fields into a single text view; the vectorizer below converts character
    # fragments into sparse vectors that remain tolerant of typos and field order.
    # fillna("") turns missing values into empty strings; astype(str) makes every
    # value text; agg(" ".join, axis=1) joins each row's values with spaces.
    return (
        df[["first_name", "last_name", "email_user", "postcode", "address"]]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
    )


def features(df: pd.DataFrame, pairs: pd.MultiIndex, vec=None) -> pd.DataFrame:
    """Build pairwise field-comparison features plus whole-record TF-IDF cosine.

    `vec` is an already fitted TfidfVectorizer; pass it when scoring new data so serving
    uses exactly the vocabulary the model was trained with.

    `df` must be indexed by unique_id and `pairs` holds (left_id, right_id) tuples.
    Returns one row per pair with 14 numeric feature columns.
    """
    # Every row in X corresponds to one candidate pair, not one customer record.
    # Keep several complementary comparisons so the classifier can learn interactions.
    # rl.Compare collects comparison definitions; nothing is computed until compute().
    c = rl.Compare()
    # Jaro-Winkler similarity (0..1) on the canonical first name; it rewards a shared
    # prefix, which suits short names.
    c.string(
        "first_name_canon", "first_name_canon", method="jarowinkler", label="first_jw"
    )
    # Two different similarities on the surname: Jaro-Winkler and normalised
    # Levenshtein (1 - edits / length). The model can learn which one is more useful.
    c.string("last_name", "last_name", method="jarowinkler", label="last_jw")
    c.string("last_name", "last_name", method="levenshtein", label="last_lev")
    # Phonetic agreement: 1 when the Metaphone codes are equal (Smith / Smyth), else 0.
    c.exact("surname_metaphone", "surname_metaphone", label="last_phonetic")
    c.exact("first_metaphone", "first_metaphone", label="first_phonetic")
    # Exact DOB agreement. missing_value=np.nan keeps "unknown" distinct from "different"
    # (0); the gradient boosting model handles NaN directly.
    c.exact("dob", "dob", label="dob_exact", missing_value=np.nan)
    # Levenshtein on the DOB text gives partial credit (a day-month swap scores 0.6).
    c.string("dob", "dob", method="levenshtein", label="dob_lev")
    # q-gram similarity: share of overlapping character chunks, robust to small typos.
    c.string("email", "email", method="qgram", label="email_qgram")
    # The part before "@", so the same username at a different provider still counts.
    c.string("email_user", "email_user", method="jarowinkler", label="email_user_jw")
    # Exact phone, full postcode and postcode area (e.g. "WR"), NaN when missing.
    c.exact("phone", "phone", label="phone_exact", missing_value=np.nan)
    c.exact("postcode", "postcode", label="postcode_exact", missing_value=np.nan)
    c.exact(
        "postcode_area",
        "postcode_area",
        label="postcode_area_exact",
        missing_value=np.nan,
    )
    # q-gram on the address, tolerant of "Road" vs "Rd" and small typos.
    c.string("address", "address", method="qgram", label="address_qgram")
    # Look up both records of every pair in df and compute the 13 columns above.
    # X is indexed by the same (left_id, right_id) MultiIndex as pairs.
    X = c.compute(pairs, df)

    # Fit only when no vectorizer is supplied. Serving/evaluation passes the training
    # vectorizer to avoid refitting its vocabulary on the records being scored.
    text = record_text(df)
    if vec is None:
        # char_wb: character n-grams taken inside word boundaries; ngram_range=(2, 4)
        # uses chunks of 2 to 4 characters. Vectors are L2-normalised by default.
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4)).fit(text)
    # One sparse row vector per record, in the same order as df.
    M = vec.transform(text)
    # Map each record ID to its row number in M.
    pos = {rid: i for i, rid in enumerate(df.index)}
    # Candidate IDs are mapped to vector-matrix row positions so each feature is the
    # cosine similarity of the two corresponding sparse record vectors.
    li = [pos[a] for a in pairs.get_level_values(0)]
    ri = [pos[b] for b in pairs.get_level_values(1)]
    # Row-wise dot product of the two normalised vectors equals their cosine similarity.
    # multiply() is element-wise, sum(axis=1) adds each row, ravel() flattens to 1-D.
    X["record_tfidf_cos"] = np.asarray(M[li].multiply(M[ri]).sum(axis=1)).ravel()
    return X


def main():
    """Train out-of-fold pair classifiers, evaluate resulting clusters, and save diagnostics."""
    raw = pd.read_csv(HERE / "data/customers.csv")
    # recordlinkage looks records up by index, so index the cleaned table by unique_id.
    df = standardise(raw).set_index("unique_id")
    # Same 6,405 candidate pairs as approach 1. candidate_pairs() expects a
    # unique_id column, hence reset_index(). Sorting makes the pair order reproducible.
    pairs = pd.MultiIndex.from_tuples(sorted(rules.candidate_pairs(df.reset_index())))
    # One row of 14 features per pair.
    X = features(df, pairs)
    truth = df["true_entity_id"]
    # Synthetic truth provides pair labels for this demo; it is deliberately not a feature.
    # Label 1 when both records belong to the same true person, else 0.
    y = (
        truth.loc[pairs.get_level_values(0)].values
        == truth.loc[pairs.get_level_values(1)].values
    ).astype(int)

    # Produce an out-of-fold probability for each pair. The fold is based on the left
    # record's person; another record for that person could still occur on the right
    # side of a training pair, so this is not the strict entity-disjoint test in step 8.
    # Fold 0 or 1 from the parity of the left record's true entity ID.
    fold = truth.loc[pairs.get_level_values(0)].values % 2
    # Filled fold by fold, so every pair gets a score from a model that did not train on it.
    proba = np.zeros(len(X))
    for f in (0, 1):
        # Boolean masks: train on the other fold, predict this fold.
        tr, te = fold != f, fold == f
        # 300 boosting rounds of small trees; random_state fixes the result.
        model = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.1, random_state=0
        )
        model.fit(X[tr], y[tr])
        # predict_proba returns [P(no match), P(match)] per row; keep the match column.
        proba[te] = model.predict_proba(X[te])[:, 1]
    print(
        f"pairs: {len(X)}, positives: {y.sum()}, average precision (out of fold): {average_precision_score(y, proba):.4f}"
    )

    # Average precision evaluates pair ranking, but one false edge can join whole
    # components. Compare several thresholds after clustering to expose that effect.
    for t in (0.5, 0.9, 0.99):
        # Pairs that pass threshold t become edges.
        m = [p for p, s in zip(pairs, proba) if s >= t]
        # Connected components over those edges, then cluster metrics.
        c = union_find_clusters(df.index, m)
        r = evaluate_clusters(df.index, df.index.map(c), truth)
        print(
            f"  threshold {t}: pair P={r['pair_precision']} R={r['pair_recall']} largest cluster={r['largest_cluster']}"
        )

    # Final clustering at the chosen operating threshold.
    matched = [p for p, s in zip(pairs, proba) if s >= THRESHOLD]
    clusters = union_find_clusters(df.index, matched)
    # Predicted cluster for each record, in df.index order.
    pred = df.index.map(clusters)
    metrics = evaluate_clusters(df.index, pred, truth)
    print("quality:", metrics)

    out = HERE / "results"
    out.mkdir(exist_ok=True)
    # Features + label + out-of-fold probability per pair; reset_index turns the pair
    # MultiIndex into two columns id_l and id_r. 04_graph_resolution.py reads this file.
    scored = X.assign(label=y, ml_probability=proba).reset_index(names=["id_l", "id_r"])
    scored.to_csv(out / "pairs_ml_features.csv", index=False)
    # One metrics row tagged with the method name for 09_compare.py.
    pd.DataFrame(
        [
            {
                "method": f"recordlinkage + gradient boosting (supervised, p>={THRESHOLD})",
                **metrics,
            }
        ]
    ).to_csv(out / "metrics_ml.csv", index=False)


if __name__ == "__main__":
    main()
