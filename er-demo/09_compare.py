"""Collect the metric CSVs written by steps 1-8 into one Markdown report.

This report step does not execute matchers or recompute metrics; run the earlier steps first.
Missing inputs are skipped, so a partial run still produces a partial report.
"""

from pathlib import Path

import pandas as pd

RES = Path(__file__).parent / "results"
files = [
    "metrics_rapidfuzz.csv",
    "metrics_splink.csv",
    "metrics_ml.csv",
    "metrics_graph.csv",
]
df = pd.concat([pd.read_csv(RES / f) for f in files if (RES / f).exists()])
cols = [
    "method",
    "pair_precision",
    "pair_recall",
    "pair_f1",
    "bcubed_f1",
    "n_pred_entities",
    "n_true_entities",
    "largest_cluster",
    "false_merges_pairs",
    "missed_pairs",
]
sections = [
    "# Matcher comparison (synthetic data, known truth)\n",
    df[cols].to_markdown(index=False),
]
extras = [
    ("Households (customer spine, step 6)", "metrics_households.csv",
     ["method", "pair_precision", "pair_recall", "n_pred_entities", "n_true_entities"]),
    ("Spine data contracts (step 6)", "spine_contracts.csv", None),
    ("Identity drift between two runs (step 7)", "identity_drift.csv", None),
    ("Model registry, entity-disjoint test set (step 8)", "model_versions.csv", None),
]
for title, f, keep in extras:
    if (RES / f).exists():
        t = pd.read_csv(RES / f)
        sections += [f"\n## {title}\n", (t[keep] if keep else t).to_markdown(index=False)]
if (RES / "monitoring_report.csv").exists():
    m = pd.read_csv(RES / "monitoring_report.csv")
    head = m[m.kpi.isin(["candidate_pairs", "match_rate", "grey_zone_share", "psi_score"])]
    sections += [
        "\n## Monitoring, label-free KPIs (step 8)\n",
        head.pivot(index="kpi", columns="batch", values="value").to_markdown(),
        "\nAlerts (PSI > 0.2): "
        + (", ".join(f"{r.batch}:{r.kpi}" for r in m[m.alert].itertuples()) or "none"),
    ]
report = "\n".join(sections) + "\n"
(RES / "comparison.md").write_text(report)
print(report)
