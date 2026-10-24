"""Collect the metric CSVs written by steps 1-8 into one Markdown report.

This report step does not execute matchers or recompute metrics; run the earlier steps first.
Missing inputs are skipped, so a partial run still produces a partial report.

Reads:  results/metrics_rapidfuzz.csv, metrics_splink.csv, metrics_ml.csv, metrics_graph.csv,
        metrics_households.csv, spine_contracts.csv, identity_drift.csv,
        model_versions.csv, monitoring_report.csv (all optional except one matcher file).
Writes: results/comparison.md (and prints the same text).
Run:    python 09_compare.py   (last line of run_all.sh)
Slides: 27 (Results chart), 28 (Lessons).
"""

from pathlib import Path

import pandas as pd

# All earlier steps write their metrics into er-demo/results/.
RES = Path(__file__).parent / "results"
# One metrics file per matcher (steps 1, 2, 3) plus the graph repair rows (step 4).
files = [
    "metrics_rapidfuzz.csv",
    "metrics_splink.csv",
    "metrics_ml.csv",
    "metrics_graph.csv",
]
# Only combine matcher metrics that exist, allowing the report to describe a partial
# pipeline run as long as at least one matcher has produced its metrics file.
# pd.concat stacks the tables row-wise (one row per method).
df = pd.concat([pd.read_csv(RES / f) for f in files if (RES / f).exists()])
# Keep the comparison focused on measures that are consistently available across matchers.
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
# The report is built as a list of text blocks joined at the end.
# to_markdown (needs the tabulate package) renders a DataFrame as a Markdown table.
sections = [
    "# Matcher comparison (synthetic data, known truth)\n",
    df[cols].to_markdown(index=False),
]
# Optional sections: (heading, file name, columns to keep or None for all columns).
extras = [
    ("Households (customer spine, step 6)", "metrics_households.csv",
     ["method", "pair_precision", "pair_recall", "n_pred_entities", "n_true_entities"]),
    ("Spine data contracts (step 6)", "spine_contracts.csv", None),
    ("Identity drift between two runs (step 7)", "identity_drift.csv", None),
    ("Model registry, entity-disjoint test set (step 8)", "model_versions.csv", None),
]
for title, f, keep in extras:
    if (RES / f).exists():
        # Later stages add optional sections; omit them when those stages have not run.
        t = pd.read_csv(RES / f)
        sections += [f"\n## {title}\n", (t[keep] if keep else t).to_markdown(index=False)]
# Monitoring is stored in long format (batch, kpi, value, alert), so it gets special handling.
if (RES / "monitoring_report.csv").exists():
    m = pd.read_csv(RES / "monitoring_report.csv")
    # Show the headline operational KPIs side by side for each batch, then list the
    # individual feature/score PSI checks that crossed the configured alert threshold.
    head = m[m.kpi.isin(["candidate_pairs", "match_rate", "grey_zone_share", "psi_score"])]
    sections += [
        "\n## Monitoring, label-free KPIs (step 8)\n",
        # pivot turns long rows into a grid: one row per KPI, one column per batch.
        head.pivot(index="kpi", columns="batch", values="value").to_markdown(),
        # m[m.alert] keeps only rows flagged as alerts; "or 'none'" covers an empty list.
        "\nAlerts (PSI > 0.2): "
        + (", ".join(f"{r.batch}:{r.kpi}" for r in m[m.alert].itertuples()) or "none"),
    ]
# Join the blocks, save the report, and echo it to the console.
report = "\n".join(sections) + "\n"
(RES / "comparison.md").write_text(report)
print(report)
