# Customer matching demo: fuzzy matching, Splink, ML, Zingg and a mini MDM

Handover doc for the demo prepared for the Databricks customer-matching role (Oct 2026).
Everything runs on a laptop in about 30 seconds, on synthetic data with known truth, so every number below is measured, not claimed.

## 1. What is in here

| Step | File | What it shows | Ran here? |
|---|---|---|---|
| Data | `data/generate_data.py` | 4,000 fake UK people spread over CRM, WEB and BILLING systems, giving 8,149 records with typos, nicknames, swapped names, moved addresses, missing fields and phone/postcode formats. Also a new batch of 400 records for the incremental test. | Yes |
| Standardise | `common/standardise.py` | Name cleaning, nickname canonicalisation, email/phone/postcode normalisation, metaphone codes | Yes |
| Metrics | `common/evaluate.py` | Pairwise precision/recall/F1, B-cubed, blocking recall (pair completeness), Union-Find clustering | Yes |
| 1. Rules + fuzzy | `01_rules_rapidfuzz.py` | Blocking, a weighted rapidfuzz score, auto-match and review thresholds, connected components. This is the classic hand-built matcher. | Yes |
| 2. Splink | `02_splink.py` | Probabilistic Fellegi-Sunter model trained with EM and **no labels**, term-frequency adjustment, threshold sweep, charts (match weights, waterfall) | Yes, Splink 5.0 on DuckDB |
| 3. Supervised ML | `03_ml_recordlinkage.py` | `recordlinkage` pair features plus a char n-gram TF-IDF cosine, gradient boosting with cross-fitting by entity. This is "ML where rules fall short". | Yes |
| 4. Mini MDM | `04_mdm.py` | Stable customer ids, golden records with survivorship and field-level provenance, crosswalk, SCD2 history, review queue, steward approve/reject, incremental matching with the saved Splink model, GDPR erasure | Yes, DuckDB file `results/mdm.duckdb` |
| 5. Comparison | `05_compare.py` | Writes `results/comparison.md` | Yes |
| Zingg | `zingg/zingg_customers.py` | Zingg config with active learning phases (findTrainingData, label, train, match) | **No.** It needs Spark plus the Zingg jar or Docker image. |
| Databricks | `databricks/splink_on_databricks.py` | The same Splink model on SparkAPI, with Delta tables in Unity Catalog and MLflow logging of model and KPIs | **No.** There is no workspace here. |

## 2. How to run

For a PowerShell-ready runbook, walkthrough, and optional un-merge exercise, see [DEMO_GUIDE.md](DEMO_GUIDE.md).

```bash
cd er-demo
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
bash run_all.sh          # ~30 s, writes everything to results/
```

Open `results/splink_match_weights.html` and `results/splink_waterfall_example.html` in a browser, and query `results/mdm.duckdb` with DuckDB:

```sql
SELECT * FROM golden_record WHERE n_source_records >= 3 LIMIT 5;
SELECT * FROM xref WHERE customer_id = 'C0000007';
SELECT * FROM golden_history WHERE customer_id IN (SELECT candidate_customer_id FROM review_queue WHERE status = 'approved');
```

Tested versions: splink 5.0.0, duckdb 1.5.6, recordlinkage 0.16, rapidfuzz 3.14.6, scikit-learn 1.9.1, pandas 2.3.3, Python 3.13.

## 3. Results (seed 42, 8,149 records, 4,000 true people)

| Method | Pair precision | Pair recall | Pair F1 | B-cubed F1 | Entities found | Largest cluster | False-merge pairs | Missed pairs |
|---|---|---|---|---|---|---|---|---|
| Rules + rapidfuzz | 0.943 | 0.916 | 0.929 | 0.972 | 4,258 | 14 | 320 | 486 |
| Splink, unsupervised, p ≥ 0.95 | **0.993** | 0.965 | **0.979** | 0.989 | 4,131 | **7** | **40** | 202 |
| recordlinkage + gradient boosting, supervised, p ≥ 0.9 | 0.976 | **0.979** | 0.978 | **0.992** | 4,069 | 12 | 139 | **119** |

The blocking keeps 96.8% of true pairs and compares only 6,200 of the 33 million possible pairs.

**Mini MDM, incremental batch of 400 new records:**
- 195 records were auto-linked to existing customers, 205 became new customers, and 2 went to review.
- 194 of the 200 returning customers were attached correctly, and 1 was attached to the wrong customer.

How to read the results:
- **Splink wins on precision with zero labels.** The EM-trained m/u weights and term-frequency adjustment value an agreement on "Smith" less than an agreement on a rare surname. For customer data, precision matters most, because a false merge is a GDPR incident.
- **Supervised ML wins on recall, but it needs labels.** Here the labels come from the synthetic truth; in real life they come from data stewards reviewing the grey zone. Its pairwise average precision is about 1.0, yet clusters still chain: 37 bad edges out of 6,200 build clusters of 12–15 records. **Always evaluate clusters, not only pairs.**
- **Hand-tuned rules are the weakest and the hardest to maintain**, although they are fully explainable. Use them for the deterministic tier (same email plus same DOB) and let a model do the rest.
- Most false merges come from two different people sharing a common email pattern (e.g. `john.smith@gmail.com`). That is realistic, and it is why "generic identifier" detection matters (we did this at Mars).

## 4. The approaches in one minute each

**Rules + fuzzy (rapidfuzz / fuzzywuzzy, jellyfish, Levenshtein, Jaro-Winkler).** You choose blocking keys, similarity functions, weights and thresholds by hand. It is fast and explainable, but every new source means re-tuning, and the weights are guesses.

**Splink (MoJ, MIT licence).** It uses the Fellegi-Sunter model:
- For each field and agreement level, it learns `m = P(agree | match)` and `u = P(agree | non-match)`.
- The match weight is `log2(m/u)`, summed over the fields.
- `u` comes from random pairs and `m` from EM, so no labels are needed. Labels, when available, can estimate `m` or evaluate the model.
- Backends are DuckDB (laptop), Spark (Databricks), Athena and Postgres, so the same settings work everywhere.
- Explainability comes from waterfall charts.
- `predict_between` handles incremental matching, and the model is saved as JSON for versioning in MLflow.

**Zingg (AGPL community / commercial enterprise).** It is ML-first with active learning:
- It shows you the most uncertain pairs, and you label about 30–40 matches.
- It then learns both the blocking functions and the classifier.
- It runs on Spark and on Databricks, and has incremental runs.
- Choose it when the data is messy and you can afford a labelling session.
- Watch the AGPL licence if the code is distributed.

**Supervised classifier (recordlinkage + scikit-learn / XGBoost).** You build your own features and model. It is the most flexible, since you can add embeddings, LLM features or any business signal, but it needs labelled pairs and MLOps around it.

**Others worth naming:**
- `dedupe` (Python, active learning, BSD).
- Senzing (commercial, entity resolution as an engine, real-time).
- Databricks ARC (an automated Splink wrapper).
- Embeddings plus vector search (Databricks Vector Search, FAISS) as a blocking rule for very messy text.
- LLM-as-judge, only on the grey zone and never on every pair, because of cost and PII.
- Commercial MDM tools (Informatica MDM, Reltio, Tamr, Profisee, Semarchy) when the business wants a steward UI and workflow out of the box.

## 5. The mini MDM: what it does and why

Matching gives you clusters. MDM turns clusters into a **governed customer master** that downstream systems can trust.

| MDM concept | In `04_mdm.py` | Production on Databricks |
|---|---|---|
| Stable master id | `customer_id` from a DuckDB sequence; stable for the database lifetime (the demo's full run resets the database) | Identity table in Delta, never regenerated |
| Crosswalk | `xref(source_record_id → customer_id, probability, method)` | Delta table consumed by CRM, billing and analytics |
| Survivorship | Names and DOB: most frequent value, then source priority (CRM > BILLING > WEB). Contact data: most recent. | Same rules in Spark SQL, configured per field in a table |
| Provenance | JSON per golden record: which source and which rule won each field | Same, plus Unity Catalog lineage |
| History | `golden_history` with `valid_to` (SCD2) | Delta SCD2 / Change Data Feed |
| Grey zone | `review_queue` with p between 0.5 and 0.95; the record becomes a new customer until a steward decides | Databricks App or Streamlit for stewards; their decisions become training and evaluation labels |
| Steward actions | `approve_review` merges two customers; `reject_review` rejects a candidate; `unmerge_record` moves one source record to a new customer, rebuilds both golden records, versions history and records the reason in `steward_audit` | Same, with an audit trail |
| Incremental | New records scored only against existing ones with the **saved** Splink model (`predict_between`) | Workflow task on Change Data Feed |
| GDPR erasure | `erase_customer` removes source records, crosswalk, golden record and history | Same, plus Delta `VACUUM` and UC column masks on PII |

Still not covered: merge-on-match across customers already in the master (re-clustering) and hierarchy/households. The demo can un-merge an individual source record after a wrong attachment; full cluster splitting and re-clustering are the next things to build.

## 6. How this maps to Databricks

1. **Bronze:** one Delta table per source, loaded with Auto Loader or Lakeflow.
2. **Silver:** `customer_std`, with the same standardisation as `common/standardise.py`.
3. **Matching job:** Splink on `SparkAPI` (`databricks/splink_on_databricks.py`) writes `pairs`, `clusters` and `review_queue` to Unity Catalog.
4. **MDM job:** survivorship builds `golden_record`, `xref` and `golden_history`.
5. **Incremental:** Change Data Feed on silver, then `predict_between`, then attach, create or review.
6. **MLflow:**
   - Log the Splink model JSON and the parameters.
   - Log the unlabelled KPIs: entities, max cluster size, review queue size, and match rate per source.
   - Once stewards have labelled pairs, also log pairwise and B-cubed precision/recall against the golden set.
   - Promote a new model to the `champion` alias only when it beats the current one.
7. **Asset Bundle** for dev/test/prod, and **Workflows** for scheduling.
8. **Feature store (optional):** standardised attributes and embeddings as a feature table keyed by `unique_id`, so training and incremental scoring use the same features.

## 7. Ten-minute demo script for the call

1. **(1 min)** "Three systems, 8k records, 4k real people. I generated them so I know the truth and can measure quality, which you never can in production."
2. **(2 min)** Rules + rapidfuzz: "This is what I built before, at CloserStill and Mars: blocking, weighted fuzzy scoring, thresholds, Union-Find. F1 is 0.93, and there is a 14-record cluster from chaining."
3. **(3 min)** Splink: "Same blocking, but the weights are learned with EM and no labels. Precision goes from 0.94 to 0.99, and the largest cluster drops to 7." Then open the waterfall chart: "This is how I explain a match to a data steward."
4. **(1 min)** ML: "With labels from stewards, a classifier gets the best recall. But look: pairwise AP is 1.0 and clusters still chain, so I evaluate at cluster level, with B-cubed."
5. **(2 min)** MDM: "Clusters become a customer master: stable ids, survivorship with provenance, crosswalk, history, review queue, incremental with the saved model, and GDPR erasure."
6. **(1 min)** Databricks mapping (section 6), and close with: "for your framework I'd start with Splink on Spark, add the steward loop for labels, and only add an ML or Zingg layer where Splink's grey zone is big."

## 8. Honest limits

- **Synthetic data is cleaner than real data.** Real data has shared family emails, company records mixed with people, transliterated names and junk values like `test@test.com`. Expect lower numbers.
- **Some Splink levels are untrained.** Splink warns that a few `dob` and `postcode` levels stay untrained, because the generator never produces near-miss DOBs or same-sector postcodes. Real data trains them.
- **Zingg and the Databricks notebook were not executed here.** Check them against the installed versions before showing them live.
- **The MDM is a teaching model, not a product.** It supports a steward-driven single-record un-merge, but has no general cluster-split workflow, concurrency control or UI.

## 9. Files after a run

`results/comparison.md`, `metrics_*.csv`, `clusters_*.csv`, `pairs_splink.csv`, `review_queue_*.csv`, `splink_model.json`, `splink_*.html`, `splink_threshold_sweep.csv`, `pairs_ml_features.csv`, `mdm.duckdb`, `mdm_golden_record.csv`, `mdm_xref.csv`, `mdm_review_queue.csv`.
