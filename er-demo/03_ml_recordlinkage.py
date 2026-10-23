"""Approach 3: supervised ML matcher with the `recordlinkage` toolkit + scikit-learn.

"ML where rules fall short": when you have labelled pairs (from data stewards reviewing the
grey zone), train a classifier on pair features. Here labels come from the synthetic truth.

- indexing: same blocking keys as approach 1 (recordlinkage.Index also has block / sortedneighbourhood)
- features: string similarities (Jaro-Winkler, Levenshtein, q-gram), exact matches, date and
  phonetic agreement, plus a char-n-gram TF-IDF cosine of the whole record (cheap "embedding")
- model: gradient boosting, 2-fold cross-fitting by the left record's entity. This is
  out-of-fold scoring, but is not a strict entity-disjoint split; step 8 shows that version.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import recordlinkage as rl
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import average_precision_score

sys.path.insert(0, str(Path(__file__).parent))
from common.evaluate import evaluate_clusters, union_find_clusters  # noqa: E402
from common.standardise import standardise  # noqa: E402

rules = __import__("01_rules_rapidfuzz")  # reuse the blocking from approach 1

HERE = Path(__file__).parent
THRESHOLD = 0.9


def record_text(df: pd.DataFrame) -> pd.Series:
    """One string per record for the whole-record TF-IDF feature."""
    # Join fields into a single text view; the vectorizer below converts character
    # fragments into sparse vectors that remain tolerant of typos and field order.
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
    """
    # Every row in X corresponds to one candidate pair, not one customer record.
    # Keep several complementary comparisons so the classifier can learn interactions.
    c = rl.Compare()
    c.string(
        "first_name_canon", "first_name_canon", method="jarowinkler", label="first_jw"
    )
    c.string("last_name", "last_name", method="jarowinkler", label="last_jw")
    c.string("last_name", "last_name", method="levenshtein", label="last_lev")
    c.exact("surname_metaphone", "surname_metaphone", label="last_phonetic")
    c.exact("first_metaphone", "first_metaphone", label="first_phonetic")
    c.exact("dob", "dob", label="dob_exact", missing_value=np.nan)
    c.string("dob", "dob", method="levenshtein", label="dob_lev")
    c.string("email", "email", method="qgram", label="email_qgram")
    c.string("email_user", "email_user", method="jarowinkler", label="email_user_jw")
    c.exact("phone", "phone", label="phone_exact", missing_value=np.nan)
    c.exact("postcode", "postcode", label="postcode_exact", missing_value=np.nan)
    c.exact(
        "postcode_area",
        "postcode_area",
        label="postcode_area_exact",
        missing_value=np.nan,
    )
    c.string("address", "address", method="qgram", label="address_qgram")
    X = c.compute(pairs, df)

    # Fit only when no vectorizer is supplied. Serving/evaluation passes the training
    # vectorizer to avoid refitting its vocabulary on the records being scored.
    text = record_text(df)
    if vec is None:
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4)).fit(text)
    M = vec.transform(text)
    pos = {rid: i for i, rid in enumerate(df.index)}
    # Candidate IDs are mapped to vector-matrix row positions so each feature is the
    # cosine similarity of the two corresponding sparse record vectors.
    li = [pos[a] for a in pairs.get_level_values(0)]
    ri = [pos[b] for b in pairs.get_level_values(1)]
    X["record_tfidf_cos"] = np.asarray(M[li].multiply(M[ri]).sum(axis=1)).ravel()
    return X


def main():
    """Train out-of-fold pair classifiers, evaluate resulting clusters, and save diagnostics."""
    raw = pd.read_csv(HERE / "data/customers.csv")
    df = standardise(raw).set_index("unique_id")
    pairs = pd.MultiIndex.from_tuples(sorted(rules.candidate_pairs(df.reset_index())))
    X = features(df, pairs)
    truth = df["true_entity_id"]
    # Synthetic truth provides pair labels for this demo; it is deliberately not a feature.
    y = (
        truth.loc[pairs.get_level_values(0)].values
        == truth.loc[pairs.get_level_values(1)].values
    ).astype(int)

    # Produce an out-of-fold probability for each pair. The fold is based on the left
    # record's person; another record for that person could still occur on the right
    # side of a training pair, so this is not the strict entity-disjoint test in step 8.
    fold = truth.loc[pairs.get_level_values(0)].values % 2
    proba = np.zeros(len(X))
    for f in (0, 1):
        tr, te = fold != f, fold == f
        model = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.1, random_state=0
        )
        model.fit(X[tr], y[tr])
        proba[te] = model.predict_proba(X[te])[:, 1]
    print(
        f"pairs: {len(X)}, positives: {y.sum()}, average precision (out of fold): {average_precision_score(y, proba):.4f}"
    )

    # Average precision evaluates pair ranking, but one false edge can join whole
    # components. Compare several thresholds after clustering to expose that effect.
    for t in (0.5, 0.9, 0.99):
        m = [p for p, s in zip(pairs, proba) if s >= t]
        c = union_find_clusters(df.index, m)
        r = evaluate_clusters(df.index, df.index.map(c), truth)
        print(
            f"  threshold {t}: pair P={r['pair_precision']} R={r['pair_recall']} largest cluster={r['largest_cluster']}"
        )

    matched = [p for p, s in zip(pairs, proba) if s >= THRESHOLD]
    clusters = union_find_clusters(df.index, matched)
    pred = df.index.map(clusters)
    metrics = evaluate_clusters(df.index, pred, truth)
    print("quality:", metrics)

    out = HERE / "results"
    out.mkdir(exist_ok=True)
    scored = X.assign(label=y, ml_probability=proba).reset_index(names=["id_l", "id_r"])
    scored.to_csv(out / "pairs_ml_features.csv", index=False)
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
