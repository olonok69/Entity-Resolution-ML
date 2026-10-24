#!/usr/bin/env bash
# Run the whole entity-resolution demo end to end, in pipeline order (slide 4).
# Usage: ./run_all.sh            (uses python3)
#        PYTHON=.venv/bin/python ./run_all.sh   (pick a specific interpreter)
# Each step reads files written by the steps before it, so the order matters.

# Stop at the first failing step, so later steps never run on stale or missing inputs.
set -e
# Move to the folder containing this script, so relative paths work from anywhere.
cd "$(dirname "$0")"
# ${PYTHON:-python3} means: use $PYTHON if set, otherwise python3.
# 0. Synthetic data with known truth -> data/customers.csv, data/new_batch.csv (slide 5).
"${PYTHON:-python3}" data/generate_data.py
# 1. Hand-built rules + rapidfuzz scores (slides 7, 8).
"${PYTHON:-python3}" 01_rules_rapidfuzz.py
# 2. Splink Fellegi-Sunter model trained with EM, no labels (slides 9, 10).
"${PYTHON:-python3}" 02_splink.py
# 3. Supervised pair classifier with recordlinkage features (slides 11 to 13).
"${PYTHON:-python3}" 03_ml_recordlinkage.py
# 4. Graph repair: cannot-link constraints and minimum cut (slides 15 to 17).
"${PYTHON:-python3}" 04_graph_resolution.py
# 5. Mini MDM: golden records, crosswalk, incremental batch (slide 19).
"${PYTHON:-python3}" 05_mdm.py
# 6. Customer spine, households and hierarchy (slide 20).
"${PYTHON:-python3}" 06_customer_spine.py
# 7. Identity drift: stable customer ids across two runs (slide 21).
"${PYTHON:-python3}" 07_identity_drift.py
# 8. Feature store, model registry, promotion gate and monitoring (slides 23, 24).
"${PYTHON:-python3}" 08_mlops_feature_store.py
# 9. Collect every metrics CSV into results/comparison.md (slide 27).
"${PYTHON:-python3}" 09_compare.py
