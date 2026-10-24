"""Step 8: MLOps for the ML matcher: feature store, model registry, promotion gate, monitoring.

03_ml_recordlinkage.py shows that a pair classifier works. This step shows how you would
run it as a product:

  feature store   pair features live in a versioned table (results/feature_store.duckdb)
                  keyed by (id_l, id_r) with the feature-set version and compute time.
                  Training and scoring both read from it, with the same fitted TF-IDF, so
                  there is no training/serving skew. A model refuses features of another version.
  evaluation      a strict entity-disjoint split: a person is either in train or in test,
                  never both. Metrics: average precision, Brier score and expected calibration
                  error (is p=0.9 really right 90% of the time?), and B-cubed on test clusters.
  registry        every model version is saved with its metrics and feature-set version in
                  results/model_registry/. A challenger replaces the champion only if it
                  passes the promotion gate.
  monitoring      score the incoming batch and compute label-free KPIs: match rate, grey-zone
                  share, and population stability index (PSI) of the score and of each feature
                  against training. A simulated broken feed shows the alerts firing.

If `mlflow` is installed, the same runs are also logged to results/mlruns (optional).
Run 03_ml_recordlinkage.py's dependencies first (data generation); this step is self-contained.

Inputs:
    data/customers.csv     training snapshot with true_entity_id (labels come from it)
    data/new_batch.csv     incoming batch used for monitoring (and a broken copy of it)

Outputs:
    results/feature_store.duckdb          feature_definitions + pair_features_* tables
    results/model_registry/               matcher_v1.pkl, matcher_v2.pkl, registry.json
    results/model_versions.csv, results/monitoring_report.csv
    results/mlruns/                       only if mlflow is installed

How to run:
    python 08_mlops_feature_store.py      (after data/generate_data.py)

Related slides: 22 (section MLOps), 23 (feature store, registry, gate), 24 (monitoring),
25 (lakehouse mapping), 13 (precision or recall).
"""

# hashlib builds the feature-set version; json stores the registry; pickle saves models.
import hashlib
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

# DuckDB is the embedded database that plays the role of the offline feature store.
import duckdb
import numpy as np
import pandas as pd
# Two candidate model families: a boosted tree ensemble and a linear baseline.
from sklearn.ensemble import HistGradientBoostingClassifier
# TF-IDF over character n-grams turns each whole record into a vector (one feature).
from sklearn.feature_extraction.text import TfidfVectorizer
# The linear model cannot accept NaN, so missing comparisons are imputed first.
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
# average_precision_score: area under the precision-recall curve (ranking quality).
# brier_score_loss: mean squared error of the probabilities (lower is better).
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# Make the local "common" package importable when the script is run from any folder.
sys.path.insert(0, str(Path(__file__).parent))
# evaluate_clusters scores clusters against truth; union_find_clusters turns matched
# pairs into connected components (one cluster id per record).
from common.evaluate import evaluate_clusters, union_find_clusters  # noqa: E402
# standardise cleans names, phones, emails and adds phonetic keys, as in steps 1 to 3.
from common.standardise import standardise  # noqa: E402

# File names start with a digit, so a normal "import" statement cannot load them;
# __import__ with the module name as a string can. Reusing them keeps blocking and
# features identical to the earlier steps.
rules = __import__("01_rules_rapidfuzz")  # blocking
ml_step = __import__("03_ml_recordlinkage")  # pair features

HERE = Path(__file__).parent
RES = HERE / "results"
REGISTRY = RES / "model_registry"
# Decision threshold: a pair with p >= 0.9 is a match (same value as step 3).
THRESHOLD = 0.9
PSI_ALERT = 0.2  # common rule of thumb: < 0.1 stable, 0.1-0.2 watch, > 0.2 act


def now():
    # UTC timestamp string used for every created_at / computed_at / registered_at.
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- feature store ----------
class FeatureStore:
    """A tiny offline feature store: versioned pair features in DuckDB."""

    def __init__(self, path: Path):
        # One DuckDB file holds the feature catalogue and all feature tables.
        self.con = duckdb.connect(str(path))
        # The catalogue documents which features belong to which feature-set version.
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS feature_definitions (
                feature_set_version VARCHAR, feature_name VARCHAR, description VARCHAR,
                created_at VARCHAR)""")

    @staticmethod
    def version(feature_names: list[str], vec: TfidfVectorizer) -> str:
        """Feature-set version = hash of feature names and the fitted TF-IDF vocabulary."""
        # Hash the sorted feature names first. Sorting makes the version independent
        # of column order.
        h = hashlib.sha256(json.dumps(sorted(feature_names)).encode())
        # Then mix in the fitted vocabulary (vocabulary_ maps each n-gram to a column).
        # Refitting TF-IDF on other data changes the vocabulary and so the version.
        h.update(json.dumps(sorted(vec.vocabulary_)).encode())
        # A short readable id such as "fs_dc5909e646".
        return "fs_" + h.hexdigest()[:10]

    def register(self, version: str, names: list[str]):
        """Record the feature definitions once per feature-set version."""
        # Idempotent: if this version is already in the catalogue, do nothing.
        if self.con.execute(
            "SELECT count(*) FROM feature_definitions WHERE feature_set_version = ?",
            [version],
        ).fetchone()[0]:
            return
        # One catalogue row per feature; scalar values are repeated for every row.
        defs = pd.DataFrame(
            {
                "feature_set_version": version,
                "feature_name": names,
                "description": [f"pair comparison feature {n}" for n in names],
                "created_at": now(),
            }
        )
        # Expose the DataFrame to SQL, append it, then drop the temporary view.
        self.con.register("defs", defs)
        self.con.execute("INSERT INTO feature_definitions SELECT * FROM defs")
        self.con.unregister("defs")

    def write(self, table: str, X: pd.DataFrame, version: str):
        """Write a pair-feature table (one per use: training, serving batch)."""
        # Persist the pair IDs with the values so training and later scoring can use
        # the same named feature set and verify which version produced each row.
        # reset_index turns the (left id, right id) MultiIndex into columns id_l, id_r.
        out = X.reset_index(names=["id_l", "id_r"]).assign(
            feature_set_version=version, computed_at=now()
        )
        self.con.register("fx", out)
        # CREATE OR REPLACE overwrites the table, so a rerun never mixes old and new rows.
        self.con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM fx")
        self.con.unregister("fx")

    def read(self, table: str, version: str) -> pd.DataFrame:
        """Read features, refusing a feature-set version the model was not trained on."""
        df = self.con.execute(f"SELECT * FROM {table}").df()
        # All versions present in the table; a clean table has exactly one.
        found = set(df.feature_set_version)
        # A version mismatch is training/serving skew, so fail instead of scoring silently.
        if found != {version}:
            raise ValueError(f"{table} has feature set {found}, model expects {version}")
        # Return the same shape the model was trained on: pair index, feature columns only.
        return df.set_index(["id_l", "id_r"]).drop(
            columns=["feature_set_version", "computed_at"]
        )


# ---------- evaluation ----------
def ece(y, p, bins=10) -> float:
    """Expected calibration error: average |observed match rate - predicted p| per bin."""
    # Bin predicted probabilities and weight each calibration gap by the fraction
    # of examples in that bin; lower ECE means probabilities better reflect outcomes.
    # 11 edges 0.0, 0.1, ..., 1.0 define 10 equal-width bins.
    edges = np.linspace(0, 1, bins + 1)
    # np.digitize returns the bin number (1-based) for each p; shift to 0-based and
    # clip so that p = 1.0 falls in the last bin instead of an 11th one.
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    total = 0.0
    for b in range(bins):
        m = idx == b  # boolean mask of the pairs in this bin
        if m.any():
            # m.mean() is the share of pairs in the bin; y[m].mean() is the observed
            # match rate there and p[m].mean() the average predicted probability.
            total += m.mean() * abs(y[m].mean() - p[m].mean())
    return round(float(total), 4)


def psi(expected, actual, bins=10) -> float:
    """Population stability index between a reference and a new distribution."""
    # PSI = sum over buckets of (actual% - expected%) * ln(actual% / expected%).
    # 0 means identical distributions; larger means the new data looks different.
    expected, actual = np.asarray(expected, float), np.asarray(actual, float)
    # Bucket edges are the deciles of the reference data (ignoring NaN). np.unique
    # removes repeated edges, which happen for binary features such as phone_exact.
    qs = np.unique(np.nanquantile(expected, np.linspace(0, 1, bins + 1)))

    def dist(x):
        # Share of values in each bucket, plus one extra bucket for missing values.
        nan = np.isnan(x)
        # np.histogram counts non-missing values per bucket. If all edges collapsed
        # into one (a constant feature), use a single bucket holding every value.
        counts = np.histogram(x[~nan], bins=qs)[0] if len(qs) > 1 else np.array([(~nan).sum()])
        # Keep missing values as their own bucket so changes in null rates can trigger PSI.
        d = np.append(counts, nan.sum()) / len(x)
        # Replace empty buckets with a tiny share so log(a / e) never divides by zero.
        return np.clip(d, 1e-4, None)

    # Reuse reference quantiles for both distributions so each bucket is comparable.
    e, a = dist(expected), dist(actual)
    return round(float(np.sum((a - e) * np.log(a / e))), 4)


def evaluate(model, X, y, records, pairs, truth) -> dict:
    """Pair ranking, calibration and cluster quality on the held-out people."""
    # predict_proba returns one column per class; column 1 is P(match).
    p = model.predict_proba(X)[:, 1]
    # Pairs above the threshold become edges; connected components become customers.
    matched = [pr for pr, s in zip(pairs, p) if s >= THRESHOLD]
    clusters = union_find_clusters(records, matched)
    # Compare predicted clusters of the test records with their true person ids.
    m = evaluate_clusters(records, [clusters[r] for r in records], truth.loc[records])
    return {
        # Pair-level metrics: how well scores rank matches, and how honest they are.
        "average_precision": round(float(average_precision_score(y, p)), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "ece": ece(y, p),
        # Cluster-level metrics: what a downstream customer table would experience.
        "bcubed_f1": m["bcubed_f1"],
        "pair_precision": m["pair_precision"],
        "pair_recall": m["pair_recall"],
        # The biggest cluster size is a cheap chaining (over-merge) detector.
        "largest_cluster": int(m["largest_cluster"]),
    }


# ---------- registry ----------
def load_registry() -> dict:
    # The registry is one JSON file: a list of versions and a map of aliases
    # (for example {"champion": 2}). Start empty when the file does not exist yet.
    f = REGISTRY / "registry.json"
    return json.loads(f.read_text()) if f.exists() else {"versions": [], "aliases": {}}


def save_registry(reg: dict):
    # Persist the registry after all versions have been registered and gated.
    (REGISTRY / "registry.json").write_text(json.dumps(reg, indent=1))


def register(reg: dict, name: str, model, metrics: dict, fs_version: str) -> dict:
    """Save a model artifact and its metadata as the next version."""
    # Versions are simple increasing integers: 1, 2, 3, ...
    version = len(reg["versions"]) + 1
    # Serialise the fitted model to a file; this is the artifact a scorer would load.
    path = REGISTRY / f"matcher_v{version}.pkl"
    path.write_bytes(pickle.dumps(model))
    # Metadata ties the artifact to the exact feature-set version and threshold it
    # needs, plus the test metrics used by the promotion gate.
    entry = {
        "version": version,
        "model_type": name,
        "feature_set_version": fs_version,
        "threshold": THRESHOLD,
        "metrics": metrics,
        "artifact": path.name,
        "registered_at": now(),
    }
    reg["versions"].append(entry)
    return entry


def promotion_gate(challenger: dict, champion: dict | None) -> tuple[bool, str]:
    """Promote only if cluster quality is at least as good and calibration is acceptable."""
    # Reject poor calibration first; after a champion exists, also protect cluster
    # quality and guard against a substantial increase in chaining.
    c = challenger["metrics"]
    # Gate 1: probabilities drive auto-link and review thresholds, so they must be honest.
    if c["ece"] > 0.05:
        return False, f"calibration too poor (ECE {c['ece']})"
    # First acceptable model becomes champion by default.
    if champion is None:
        return True, "no champion yet"
    k = champion["metrics"]
    # Gate 2: cluster quality (B-cubed F1) must not get worse than the current champion.
    if c["bcubed_f1"] < k["bcubed_f1"]:
        return False, f"B-cubed F1 {c['bcubed_f1']} < champion {k['bcubed_f1']}"
    # Gate 3: a much larger biggest cluster signals chaining (false merges via weak links).
    if c["largest_cluster"] > k["largest_cluster"] + 2:
        return False, "more chaining than the champion"
    return True, f"B-cubed F1 {c['bcubed_f1']} >= champion {k['bcubed_f1']}"


def log_to_mlflow(entry: dict, promoted: bool):
    """Optional: mirror the registry entry to a local MLflow tracking store."""
    # MLflow is optional; without it the JSON registry above is the only record.
    try:
        import mlflow
    except ImportError:
        return
    # Store runs in a local folder (file:// URI) under one experiment name.
    mlflow.set_tracking_uri((RES / "mlruns").as_uri())
    mlflow.set_experiment("customer-matcher")
    # One MLflow run per model version, with params, metrics, the gate decision and the pickle.
    with mlflow.start_run(run_name=f"v{entry['version']}_{entry['model_type']}"):
        mlflow.log_params(
            {k: entry[k] for k in ("model_type", "feature_set_version", "threshold")}
        )
        mlflow.log_metrics(entry["metrics"])
        mlflow.set_tag("promoted", promoted)
        mlflow.log_artifact(str(REGISTRY / entry["artifact"]))


# ---------- monitoring ----------
def batch_pairs(existing: pd.DataFrame, new: pd.DataFrame) -> pd.MultiIndex:
    """Candidate pairs between existing and new records, with the same blocking keys."""
    # Block on the union of old and new records, using the step 1 blocking keys.
    both = pd.concat([existing, new])
    new_ids = set(new.unique_id)
    # Retain only cross-snapshot comparisons (one old, one new) and put old IDs on
    # the left, matching the feature/model convention used by the rest of the demo.
    # "(a in new_ids) != (b in new_ids)" is true when exactly one side is new
    # (old-old pairs were scored in training, new-new pairs are out of scope here).
    pairs = {
        (a, b) if a not in new_ids else (b, a)
        for a, b in rules.candidate_pairs(both)
        if (a in new_ids) != (b in new_ids)
    }
    # Sorted MultiIndex of (id_l, id_r), the pair format recordlinkage expects.
    return pd.MultiIndex.from_tuples(sorted(pairs))


def monitor(name, model, X_ref, p_ref, X_new) -> list[dict]:
    """Label-free KPIs for one scored batch, with PSI alerts."""
    # Score the new batch. No labels exist in production, so every KPI here is label-free.
    p = model.predict_proba(X_new)[:, 1]
    rows = [
        # Volume: a drop in candidate pairs means blocking keys (e.g. phone) are missing.
        {"batch": name, "kpi": "candidate_pairs", "value": len(X_new), "alert": False},
        # Share of pairs auto-matched at the threshold.
        {"batch": name, "kpi": "match_rate", "value": round(float((p >= THRESHOLD).mean()), 4), "alert": False},
        # Share of uncertain pairs (0.5 <= p < 0.9): the load sent to human review.
        {"batch": name, "kpi": "grey_zone_share", "value": round(float(((p >= 0.5) & (p < THRESHOLD)).mean()), 4), "alert": False},
    ]
    # Score drift: compare the batch score distribution with the training scores.
    s = psi(p_ref, p)
    rows.append({"batch": name, "kpi": "psi_score", "value": s, "alert": s > PSI_ALERT})
    # Feature drift: one PSI per feature, so an alert points at the broken input.
    for col in X_ref.columns:
        v = psi(X_ref[col], X_new[col])
        rows.append({"batch": name, "kpi": f"psi_{col}", "value": v, "alert": v > PSI_ALERT})
    return rows


def main():
    """Feature store -> two model versions -> promotion gate -> monitoring of two batches."""
    RES.mkdir(exist_ok=True)
    REGISTRY.mkdir(exist_ok=True)
    (REGISTRY / "registry.json").unlink(missing_ok=True)  # demo run starts a fresh registry
    # Also start a fresh feature store file, so the demo is repeatable.
    fs_path = RES / "feature_store.duckdb"
    fs_path.unlink(missing_ok=True)
    store = FeatureStore(fs_path)

    # Load and standardise the training snapshot; unique_id becomes the row index.
    raw = pd.read_csv(HERE / "data/customers.csv")
    df = standardise(raw).set_index("unique_id")
    # True person id per record: the source of training labels and test truth.
    truth = df["true_entity_id"]
    # Same blocking as step 1; sorted so the pair order (and results) are reproducible.
    pairs = pd.MultiIndex.from_tuples(sorted(rules.candidate_pairs(df.reset_index())))

    # Fit TF-IDF once on the training records (char_wb = character n-grams of 2 to 4
    # inside word boundaries). The same fitted object is reused for every later batch.
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4)).fit(ml_step.record_text(df))
    # One row per candidate pair, one column per comparison feature (step 3's features()).
    X = ml_step.features(df, pairs, vec)
    # Version the feature set, document it in the catalogue and store the training rows.
    fs_version = FeatureStore.version(list(X.columns), vec)
    store.register(fs_version, list(X.columns))
    store.write("pair_features_train", X, fs_version)
    print(f"feature store: {len(X)} pair rows, {X.shape[1]} features, version {fs_version}")

    # training reads from the store, exactly as a scheduled job would
    X = store.read("pair_features_train", fs_version)
    # Label = 1 when both records of the pair belong to the same true person.
    # get_level_values(0) / (1) are the left and right record ids of each pair.
    y = (truth.loc[X.index.get_level_values(0)].values == truth.loc[X.index.get_level_values(1)].values).astype(int)

    # strict entity-disjoint split: a person is in train or in test, never both
    # Choose a third of the people (fixed seed 0) as test people.
    ents = np.array(sorted(truth.unique()))
    test_ents = set(np.random.default_rng(0).choice(ents, size=len(ents) // 3, replace=False))
    # Per record: is it a test person? Then look it up for the left and right side of each pair.
    in_test = truth.isin(test_ents)
    l_test = in_test.loc[X.index.get_level_values(0)].values
    r_test = in_test.loc[X.index.get_level_values(1)].values
    # Exclude cross-boundary pairs: training has no test people, and test pairs are all test people.
    tr, te = ~l_test & ~r_test, l_test & r_test
    # All records of test people: the population on which clusters are evaluated.
    test_records = list(truth.index[in_test])
    print(f"entity-disjoint split: {tr.sum()} train pairs, {te.sum()} test pairs")

    # Compare a linear baseline with a nonlinear model under the same split, features,
    # and promotion rules; this isolates the model choice for the demonstration.
    candidates = {
        # Missing comparisons (NaN) become 0, features are scaled, then a logistic model.
        "logistic_regression": make_pipeline(
            SimpleImputer(strategy="constant", fill_value=0), StandardScaler(), LogisticRegression(max_iter=1000)
        ),
        # Gradient boosting handles NaN natively and learns field interactions.
        "gradient_boosting": HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, random_state=0),
    }
    reg = load_registry()
    # Each candidate is trained, evaluated, registered and gated in order, so v2 is
    # compared against whichever version is champion after v1.
    for name, model in candidates.items():
        model.fit(X[tr], y[tr])
        metrics = evaluate(model, X[te], y[te], test_records, list(X.index[te]), truth)
        entry = register(reg, name, model, metrics, fs_version)
        # Look up the version the "champion" alias points to (None on the first loop).
        champion = next((v for v in reg["versions"] if v["version"] == reg["aliases"].get("champion")), None)
        ok, why = promotion_gate(entry, champion)
        # Promotion only moves the alias; the old version stays in the registry.
        if ok:
            reg["aliases"]["champion"] = entry["version"]
        print(f"v{entry['version']} {name}: {metrics} -> {'PROMOTED' if ok else 'kept as challenger'} ({why})")
        log_to_mlflow(entry, ok)
    save_registry(reg)

    # Serving loads the champion by alias from the registry, not from memory.
    champion = next(v for v in reg["versions"] if v["version"] == reg["aliases"]["champion"])
    model = pickle.loads((REGISTRY / champion["artifact"]).read_bytes())
    # Reference score distribution for PSI: the champion's scores on the training pairs.
    p_ref = model.predict_proba(X[tr])[:, 1]

    # Compare a normal incoming batch with a controlled failure scenario. The latter
    # simulates missing phones and names reduced to initials to demonstrate drift alerts.
    batch = pd.read_csv(HERE / "data/new_batch.csv")
    broken = batch.assign(
        phone=None,  # a source stopped sending phone numbers
        first_name=batch.first_name.str[0],  # a new web form captures initials only
    )
    report = []
    for name, b in [("new_batch", batch), ("broken_feed", broken)]:
        # Standardise the batch exactly as the training data was.
        new = standardise(b).set_index("unique_id")
        # Features need both sides of a pair, so look records up in old + new together.
        allrec = pd.concat([df, new])
        bp = batch_pairs(df.reset_index(), new.reset_index())
        Xb = ml_step.features(allrec, bp, vec)  # same fitted vectorizer as training
        # Write through the store and read back with the champion's feature-set version:
        # this is the skew check a real scoring job would perform.
        store.write(f"pair_features_{name}", Xb, fs_version)
        Xb = store.read(f"pair_features_{name}", champion["feature_set_version"])
        rows = monitor(name, model, X[tr], p_ref, Xb)
        report += rows
        # Names of KPIs that crossed the PSI threshold, and the four headline KPIs.
        alerts = [r["kpi"] for r in rows if r["alert"]]
        kpis = {r["kpi"]: r["value"] for r in rows[:4]}
        print(f"monitoring {name}: {kpis} alerts: {alerts or 'none'}")
    # Long-format monitoring table (batch, kpi, value, alert) for 09_compare.py.
    pd.DataFrame(report).to_csv(RES / "monitoring_report.csv", index=False)
    # One row per registered version with its metrics flattened into columns.
    pd.DataFrame(
        [{"version": v["version"], "model_type": v["model_type"], **v["metrics"]} for v in reg["versions"]]
    ).to_csv(RES / "model_versions.csv", index=False)
    store.con.close()


# Run main() only when executed as a script, not when imported by another module.
if __name__ == "__main__":
    main()
