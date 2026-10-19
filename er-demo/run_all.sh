#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
"${PYTHON:-python3}" data/generate_data.py
"${PYTHON:-python3}" 01_rules_rapidfuzz.py
"${PYTHON:-python3}" 02_splink.py
"${PYTHON:-python3}" 03_ml_recordlinkage.py
"${PYTHON:-python3}" 04_mdm.py
"${PYTHON:-python3}" 05_compare.py
