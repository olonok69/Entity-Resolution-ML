"""Collect existing matcher metric CSVs into a Markdown comparison table.

This report step does not execute matchers or recompute metrics; run approaches 1-3 first.
"""

from pathlib import Path

import pandas as pd

RES = Path(__file__).parent / "results"
files = ["metrics_rapidfuzz.csv", "metrics_splink.csv", "metrics_ml.csv"]
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
table = df[cols].to_markdown(index=False)
(RES / "comparison.md").write_text(
    "# Matcher comparison (synthetic data, known truth)\n\n" + table + "\n"
)
print(table)
