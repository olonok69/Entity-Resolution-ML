#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
"${PYTHON:-python3}" data/generate_data.py
"${PYTHON:-python3}" 01_rules_rapidfuzz.py
"${PYTHON:-python3}" 02_splink.py
"${PYTHON:-python3}" 03_ml_recordlinkage.py
"${PYTHON:-python3}" 04_graph_resolution.py
"${PYTHON:-python3}" 05_mdm.py
"${PYTHON:-python3}" 06_customer_spine.py
"${PYTHON:-python3}" 07_identity_drift.py
"${PYTHON:-python3}" 08_mlops_feature_store.py
"${PYTHON:-python3}" 09_compare.py
