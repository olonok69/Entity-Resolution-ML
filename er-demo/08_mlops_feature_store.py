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
"""

import hashlib
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent))
from common.evaluate import evaluate_clusters, union_find_clusters  # noqa: E402
from common.standardise import standardise  # noqa: E402

rules = __import__("01_rules_rapidfuzz")  # blocking
ml_step = __import__("03_ml_recordlinkage")  # pair features

HERE = Path(__file__).parent
RES = HERE / "results"
REGISTRY = RES / "model_registry"
THRESHOLD = 0.9
PSI_ALERT = 0.2  # common rule of thumb: < 0.1 stable, 0.1-0.2 watch, > 0.2 act


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- feature store ----------
class FeatureStore:
    """A tiny offline feature store: versioned pair features in DuckDB."""

    def __init__(self, path: Path):
        self.con = duckdb.connect(str(path))
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS feature_definitions (
                feature_set_version VARCHAR, feature_name VARCHAR, description VARCHAR,
                created_at VARCHAR)""")

    @staticmethod
    def version(feature_names: list[str], vec: TfidfVectorizer) -> str:
        """Feature-set version = hash of feature names and the fitted TF-IDF vocabulary."""
        h = hashlib.sha256(json.dumps(sorted(feature_names)).encode())
        h.update(json.dumps(sorted(vec.vocabulary_)).encode())
        return "fs_" + h.hexdigest()[:10]

    def register(self, version: str, names: list[str]):
        """Record the feature definitions once per feature-set version."""
        if self.con.execute(
            "SELECT count(*) FROM feature_definitions WHERE feature_set_version = ?",
            [version],
        ).fetchone()[0]:
            return
        defs = pd.DataFrame(
            {
                "feature_set_version": version,
                "feature_name": names,
                "description": [f"pair comparison feature {n}" for n in names],
                "created_at": now(),
            }
        )
        self.con.register("defs", defs)
        self.con.execute("INSERT INTO feature_definitions SELECT * FROM defs")
        self.con.unregister("defs")

    def write(self, table: str, X: pd.DataFrame, version: str):
        """Write a pair-feature table (one per use: training, serving batch)."""
        # Persist the pair IDs with the values so training and later scoring can use
        # the same named feature set and verify which version produced each row.
        out = X.reset_index(names=["id_l", "id_r"]).assign(
            feature_set_version=version, computed_at=now()
        )
        self.con.register("fx", out)
        self.con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM fx")
        self.con.unregister("fx")

    def read(self, table: str, version: str) -> pd.DataFrame:
        """Read features, refusing a feature-set version the model was not trained on."""
        df = self.con.execute(f"SELECT * FROM {table}").df()
        found = set(df.feature_set_version)
        # A version mismatch is training/serving skew, so fail instead of scoring silently.
        if found != {version}:
            raise ValueError(f"{table} has feature set {found}, model expects {version}")
        return df.set_index(["id_l", "id_r"]).drop(
            columns=["feature_set_version", "computed_at"]
        )


# ---------- evaluation ----------
def ece(y, p, bins=10) -> float:
    """Expected calibration error: average |observed match rate - predicted p| per bin."""
    # Bin predicted probabilities and weight each calibration gap by the fraction
    # of examples in that bin; lower ECE means probabilities better reflect outcomes.
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    total = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            total += m.mean() * abs(y[m].mean() - p[m].mean())
    return round(float(total), 4)


def psi(expected, actual, bins=10) -> float:
    """Population stability index between a reference and a new distribution."""
    expected, actual = np.asarray(expected, float), np.asarray(actual, float)
    qs = np.unique(np.nanquantile(expected, np.linspace(0, 1, bins + 1)))

    def dist(x):
        nan = np.isnan(x)
        counts = np.histogram(x[~nan], bins=qs)[0] if len(qs) > 1 else np.array([(~nan).sum()])
        # Keep missing values as their own bucket so changes in null rates can trigger PSI.
        d = np.append(counts, nan.sum()) / len(x)
        return np.clip(d, 1e-4, None)

    # Reuse reference quantiles for both distributions so each bucket is comparable.
    e, a = dist(expected), dist(actual)
    return round(float(np.sum((a - e) * np.log(a / e))), 4)


def evaluate(model, X, y, records, pairs, truth) -> dict:
    """Pair ranking, calibration and cluster quality on the held-out people."""
    p = model.predict_proba(X)[:, 1]
    matched = [pr for pr, s in zip(pairs, p) if s >= THRESHOLD]
    clusters = union_find_clusters(records, matched)
    m = evaluate_clusters(records, [clusters[r] for r in records], truth.loc[records])
    return {
        "average_precision": round(float(average_precision_score(y, p)), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "ece": ece(y, p),
        "bcubed_f1": m["bcubed_f1"],
        "pair_precision": m["pair_precision"],
        "pair_recall": m["pair_recall"],
        "largest_cluster": int(m["largest_cluster"]),
    }


# ---------- registry ----------
def load_registry() -> dict:
    f = REGISTRY / "registry.json"
    return json.loads(f.read_text()) if f.exists() else {"versions": [], "aliases": {}}


def save_registry(reg: dict):
    (REGISTRY / "registry.json").write_text(json.dumps(reg, indent=1))


def register(reg: dict, name: str, model, metrics: dict, fs_version: str) -> dict:
    """Save a model artifact and its metadata as the next version."""
    version = len(reg["versions"]) + 1
    path = REGISTRY / f"matcher_v{version}.pkl"
    path.write_bytes(pickle.dumps(model))
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
    if c["ece"] > 0.05:
        return False, f"calibration too poor (ECE {c['ece']})"
    if champion is None:
        return True, "no champion yet"
    k = champion["metrics"]
    if c["bcubed_f1"] < k["bcubed_f1"]:
        return False, f"B-cubed F1 {c['bcubed_f1']} < champion {k['bcubed_f1']}"
    if c["largest_cluster"] > k["largest_cluster"] + 2:
        return False, "more chaining than the champion"
    return True, f"B-cubed F1 {c['bcubed_f1']} >= champion {k['bcubed_f1']}"


def log_to_mlflow(entry: dict, promoted: bool):
    """Optional: mirror the registry entry to a local MLflow tracking store."""
    try:
        import mlflow
    except ImportError:
        return
    mlflow.set_tracking_uri((RES / "mlruns").as_uri())
    mlflow.set_experiment("customer-matcher")
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
    both = pd.concat([existing, new])
    new_ids = set(new.unique_id)
    # Retain only cross-snapshot comparisons (one old, one new) and put old IDs on
    # the left, matching the feature/model convention used by the rest of the demo.
    pairs = {
        (a, b) if a not in new_ids else (b, a)
        for a, b in rules.candidate_pairs(both)
        if (a in new_ids) != (b in new_ids)
    }
    return pd.MultiIndex.from_tuples(sorted(pairs))


def monitor(name, model, X_ref, p_ref, X_new) -> list[dict]:
    """Label-free KPIs for one scored batch, with PSI alerts."""
    p = model.predict_proba(X_new)[:, 1]
    rows = [
        {"batch": name, "kpi": "candidate_pairs", "value": len(X_new), "alert": False},
        {"batch": name, "kpi": "match_rate", "value": round(float((p >= THRESHOLD).mean()), 4), "alert": False},
        {"batch": name, "kpi": "grey_zone_share", "value": round(float(((p >= 0.5) & (p < THRESHOLD)).mean()), 4), "alert": False},
    ]
    s = psi(p_ref, p)
    rows.append({"batch": name, "kpi": "psi_score", "value": s, "alert": s > PSI_ALERT})
    for col in X_ref.columns:
        v = psi(X_ref[col], X_new[col])
        rows.append({"batch": name, "kpi": f"psi_{col}", "value": v, "alert": v > PSI_ALERT})
    return rows


def main():
    """Feature store -> two model versions -> promotion gate -> monitoring of two batches."""
    RES.mkdir(exist_ok=True)
    REGISTRY.mkdir(exist_ok=True)
    (REGISTRY / "registry.json").unlink(missing_ok=True)  # demo run starts a fresh registry
    fs_path = RES / "feature_store.duckdb"
    fs_path.unlink(missing_ok=True)
    store = FeatureStore(fs_path)

    raw = pd.read_csv(HERE / "data/customers.csv")
    df = standardise(raw).set_index("unique_id")
    truth = df["true_entity_id"]
    pairs = pd.MultiIndex.from_tuples(sorted(rules.candidate_pairs(df.reset_index())))

    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4)).fit(ml_step.record_text(df))
    X = ml_step.features(df, pairs, vec)
    fs_version = FeatureStore.version(list(X.columns), vec)
    store.register(fs_version, list(X.columns))
    store.write("pair_features_train", X, fs_version)
    print(f"feature store: {len(X)} pair rows, {X.shape[1]} features, version {fs_version}")

    # training reads from the store, exactly as a scheduled job would
    X = store.read("pair_features_train", fs_version)
    y = (truth.loc[X.index.get_level_values(0)].values == truth.loc[X.index.get_level_values(1)].values).astype(int)

    # strict entity-disjoint split: a person is in train or in test, never both
    ents = np.array(sorted(truth.unique()))
    test_ents = set(np.random.default_rng(0).choice(ents, size=len(ents) // 3, replace=False))
    in_test = truth.isin(test_ents)
    l_test = in_test.loc[X.index.get_level_values(0)].values
    r_test = in_test.loc[X.index.get_level_values(1)].values
    # Exclude cross-boundary pairs: training has no test people, and test pairs are all test people.
    tr, te = ~l_test & ~r_test, l_test & r_test
    test_records = list(truth.index[in_test])
    print(f"entity-disjoint split: {tr.sum()} train pairs, {te.sum()} test pairs")

    # Compare a linear baseline with a nonlinear model under the same split, features,
    # and promotion rules; this isolates the model choice for the demonstration.
    candidates = {
        "logistic_regression": make_pipeline(
            SimpleImputer(strategy="constant", fill_value=0), StandardScaler(), LogisticRegression(max_iter=1000)
        ),
        "gradient_boosting": HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, random_state=0),
    }
    reg = load_registry()
    for name, model in candidates.items():
        model.fit(X[tr], y[tr])
        metrics = evaluate(model, X[te], y[te], test_records, list(X.index[te]), truth)
        entry = register(reg, name, model, metrics, fs_version)
        champion = next((v for v in reg["versions"] if v["version"] == reg["aliases"].get("champion")), None)
        ok, why = promotion_gate(entry, champion)
        if ok:
            reg["aliases"]["champion"] = entry["version"]
        print(f"v{entry['version']} {name}: {metrics} -> {'PROMOTED' if ok else 'kept as challenger'} ({why})")
        log_to_mlflow(entry, ok)
    save_registry(reg)

    champion = next(v for v in reg["versions"] if v["version"] == reg["aliases"]["champion"])
    model = pickle.loads((REGISTRY / champion["artifact"]).read_bytes())
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
        new = standardise(b).set_index("unique_id")
        allrec = pd.concat([df, new])
        bp = batch_pairs(df.reset_index(), new.reset_index())
        Xb = ml_step.features(allrec, bp, vec)  # same fitted vectorizer as training
        store.write(f"pair_features_{name}", Xb, fs_version)
        Xb = store.read(f"pair_features_{name}", champion["feature_set_version"])
        rows = monitor(name, model, X[tr], p_ref, Xb)
        report += rows
        alerts = [r["kpi"] for r in rows if r["alert"]]
        kpis = {r["kpi"]: r["value"] for r in rows[:4]}
        print(f"monitoring {name}: {kpis} alerts: {alerts or 'none'}")
    pd.DataFrame(report).to_csv(RES / "monitoring_report.csv", index=False)
    pd.DataFrame(
        [{"version": v["version"], "model_type": v["model_type"], **v["metrics"]} for v in reg["versions"]]
    ).to_csv(RES / "model_versions.csv", index=False)
    store.con.close()


if __name__ == "__main__":
    main()
