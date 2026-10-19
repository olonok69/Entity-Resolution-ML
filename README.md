# Customer Entity Resolution Demo

A laptop-sized entity-resolution and mini-MDM demo using synthetic UK customer records with known ground truth. It compares hand-built fuzzy rules, unsupervised Splink, and a supervised pair classifier, then shows incremental matching and customer-master workflows.

## Start here

- [Project overview and results](er-demo/README.md)
- [Detailed demo and code walkthrough](er-demo/DEMO_GUIDE.md)

## Quick start

From the repository root, on Windows PowerShell:

```powershell
cd er-demo
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe data/generate_data.py
.\.venv\Scripts\python.exe 01_rules_rapidfuzz.py
.\.venv\Scripts\python.exe 02_splink.py
.\.venv\Scripts\python.exe 03_ml_recordlinkage.py
.\.venv\Scripts\python.exe 04_mdm.py
.\.venv\Scripts\python.exe 05_compare.py
```

On macOS/Linux, create and activate `.venv`, install `requirements.txt`, then run `bash run_all.sh` from `er-demo/`.

The generated CSV inputs and `results/` artifacts are intentionally excluded from Git. Run the generator and pipeline to recreate them. The full `04_mdm.py` demo resets its local DuckDB database each run.

## Project layout

```text
er-demo/
  common/       shared standardisation and evaluation
  data/         synthetic data generator
  databricks/   unexecuted Databricks/SparkAPI example
  zingg/        unexecuted Zingg active-learning example
  results/      generated outputs (git-ignored)
  01_*.py ...   matching approaches, MDM, and comparison
```

All records are synthetic. `true_entity_id` is a benchmark label for evaluation and supervised training only; it is not a production matching field. Databricks and Zingg examples require their own runtimes and are not verified by the local pipeline.