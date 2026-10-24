# Customer Entity Resolution Demo

Versión en español: [README.es.md](README.es.md)

A laptop-sized customer identity resolution demo using synthetic UK customer records with known ground truth. It compares hand-built fuzzy rules, unsupervised Splink and a supervised pair classifier, repairs clusters with graph techniques, then builds a mini MDM, a governed customer spine, stable ids across runs, and the MLOps around the ML matcher (feature store, model registry, monitoring).

## Start here

- [Project overview and results](er-demo/README.md)
- [The guide: run it, learn each technique step by step, FAQ](er-demo/DEMO_GUIDE.md)
- [Code guide: every script explained block by block, linked to the code lines and the slides](er-demo/CODE_GUIDE.md)
- [Video script](er-demo/VIDEO_SCRIPT.md) and [slide deck](er-demo/slides/customer-identity-resolution.pptx)

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
.\.venv\Scripts\python.exe 04_graph_resolution.py
.\.venv\Scripts\python.exe 05_mdm.py
.\.venv\Scripts\python.exe 06_customer_spine.py
.\.venv\Scripts\python.exe 07_identity_drift.py
.\.venv\Scripts\python.exe 08_mlops_feature_store.py
.\.venv\Scripts\python.exe 09_compare.py
```

On macOS/Linux, create and activate `.venv`, install `requirements.txt`, then run `bash run_all.sh` from `er-demo/`.

The generated CSV inputs and `results/` artifacts are intentionally excluded from Git. Run the generator and pipeline to recreate them. `05_mdm.py` resets its local DuckDB database each run, and `08_mlops_feature_store.py` resets the feature store and model registry.

## Project layout

```text
er-demo/
  common/       shared standardisation and evaluation
  data/         synthetic data generator
  databricks/   unexecuted Databricks/SparkAPI example
  zingg/        unexecuted Zingg active-learning example
  slides/       slide deck for the video
  results/      generated outputs (git-ignored)
  01_*.py ...   matching approaches, graph repair, MDM, spine, drift, MLOps, report
```

All records are synthetic. `true_entity_id` and `true_household_id` are benchmark labels for evaluation and supervised training only; they are not production matching fields. Databricks and Zingg examples require their own runtimes and are not verified by the local pipeline.
