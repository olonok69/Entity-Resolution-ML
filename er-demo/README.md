# Customer identity resolution demo: fuzzy matching, Splink, ML, graphs, MDM, customer spine and MLOps

The end-to-end customer identity-resolution pipeline behind the YouTube video: from fuzzy matching to a governed customer spine.
Everything runs on a laptop in under a minute, on synthetic data with known truth, so every number below is measured, not claimed.

For the step-by-step explanations and the common questions, see [DEMO_GUIDE.md](DEMO_GUIDE.md). For the video chapters, see [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md); the slides are in [slides/](slides/customer-identity-resolution.pptx).

## 1. What is in here

| Step | File | What it shows | Ran here? |
|---|---|---|---|
| Data | `data/generate_data.py` | 4,000 fake UK people spread over CRM, WEB and BILLING systems, giving 8,192 records with typos, nicknames, swapped names, moved addresses, missing fields and phone/postcode formats. About 10% of people share a home with someone else (183 households), often with the same surname and sometimes a family email. Also a new batch of 400 records for the incremental test. | Yes |
| Standardise | `common/standardise.py` | Name cleaning, nickname canonicalisation, email/phone/postcode normalisation, metaphone codes | Yes |
| Metrics | `common/evaluate.py` | Pairwise precision/recall/F1, B-cubed, blocking recall (pair completeness), Union-Find clustering | Yes |
| 1. Rules + fuzzy | `01_rules_rapidfuzz.py` | Blocking, a weighted rapidfuzz score, auto-match and review thresholds, connected components. This is the classic hand-built matcher. | Yes |
| 2. Splink | `02_splink.py` | Probabilistic Fellegi-Sunter model trained with EM and **no labels**, term-frequency adjustment, threshold sweep, charts (match weights, waterfall) | Yes, Splink 5.0 on DuckDB |
| 3. Supervised ML | `03_ml_recordlinkage.py` | `recordlinkage` pair features plus a char n-gram TF-IDF cosine, gradient boosting with cross-fitting by entity. This is "ML where rules fall short". | Yes |
| 4. Graph resolution | `04_graph_resolution.py` | Record graph with networkx, cannot-link constraints (conflicting DOB, clearly different first name), weighted **minimum-cut repair** of chained clusters, and an identifier graph that flags emails/phones shared by several people | Yes |
| 5. Mini MDM | `05_mdm.py` | Stable customer ids, golden records with survivorship and field-level provenance, crosswalk, SCD2 history, review queue, steward approve/reject/un-merge, incremental matching with the saved Splink model, GDPR erasure | Yes, DuckDB file `results/mdm.duckdb` |
| 6. Customer spine | `06_customer_spine.py` | Governed identity hierarchy (household → customer → source record), households from an address graph, the `customer_spine` Golden Layer table, PII classification and **data contracts** that block the publish if broken | Yes, same DuckDB file |
| 7. Identity drift | `07_identity_drift.py` | Re-runs matching on a later snapshot and measures how many customer ids change under three id strategies; **carry-forward** with merge aliases and split handling | Yes |
| 8. MLOps + feature store | `08_mlops_feature_store.py` | Versioned pair features in a feature store, entity-disjoint evaluation with calibration (Brier, ECE), model registry with a champion/challenger **promotion gate**, label-free monitoring with PSI alerts on a simulated broken feed. Logs to MLflow if it is installed. | Yes, DuckDB file `results/feature_store.duckdb` |
| 9. Report | `09_compare.py` | Writes `results/comparison.md` with every table below | Yes |
| Zingg | `zingg/zingg_customers.py` | Zingg config with active learning phases (findTrainingData, label, train, match) | **No.** It needs Spark plus the Zingg jar or Docker image. |
| Databricks | `databricks/splink_on_databricks.py` | The same Splink model on SparkAPI, with Delta tables in Unity Catalog and MLflow logging of model and KPIs | **No.** There is no workspace here. |

## 2. What the demo covers

| Capability | Where the demo shows it |
|---|---|
| Graph-based techniques and entity resolution | `04_graph_resolution.py`: record graph, cannot-link constraints, min-cut repair, identifier graph. `06_customer_spine.py`: households as connected components of a customer-address graph. |
| Record linkage and fuzzy matching | `01_rules_rapidfuzz.py` (rapidfuzz, blocking, thresholds), `02_splink.py` (Fellegi-Sunter), `common/standardise.py` |
| ML-based matching where deterministic rules are insufficient | `03_ml_recordlinkage.py` (supervised), `02_splink.py` (unsupervised EM), Zingg example (active learning) |
| Customer-spine architecture and a governed identity hierarchy | `06_customer_spine.py`: `customer_spine`, `identity_hierarchy`, `household`, `column_classification`, data contracts |
| Reusable framework, reducing duplication and identity drift | Shared `common/` standardisation and metrics used by every step; one saved model reused for batch, incremental and re-runs; `07_identity_drift.py` measures and reduces drift |
| Matching-quality metrics (accuracy, confidence, model performance) | `common/evaluate.py` (pairwise, B-cubed, blocking recall), threshold sweep, calibration (Brier, ECE), label-free KPIs |
| Integrating into data platforms and the Golden Layer | `05_mdm.py` golden record + crosswalk, `06_customer_spine.py` publishes the spine, `databricks/` maps it to Delta and Unity Catalog |
| MLOps: deployment, monitoring, lifecycle | `08_mlops_feature_store.py`: registry, promotion gate, champion alias, PSI monitoring; `databricks/` MLflow logging |
| Feature stores | `08_mlops_feature_store.py`: versioned pair-feature tables, training and serving read the same features, version check |
| Customer master data and MDM | `05_mdm.py`: survivorship, provenance, SCD2, steward actions, GDPR erasure |

## 3. How to run

For a PowerShell-ready runbook and the optional un-merge exercise, see [DEMO_GUIDE.md](DEMO_GUIDE.md).

```bash
cd er-demo
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
bash run_all.sh          # ~45 s, writes everything to results/
```

Open `results/splink_match_weights.html` and `results/splink_waterfall_example.html` in a browser, and query `results/mdm.duckdb` with DuckDB:

```sql
SELECT * FROM golden_record WHERE n_source_records >= 3 LIMIT 5;
SELECT * FROM xref WHERE customer_id = 'C0000007';
SELECT * FROM golden_history WHERE customer_id IN (SELECT candidate_customer_id FROM review_queue WHERE status = 'approved');
SELECT * FROM customer_spine WHERE household_size > 1 ORDER BY household_id LIMIT 6;
SELECT * FROM identity_hierarchy WHERE parent_id = 'H0000023' OR node_id = 'H0000023';
```

Tested versions: splink 5.0.0, duckdb 1.5.6, recordlinkage 0.16, rapidfuzz 3.14.6, scikit-learn 1.9.1, networkx 3.7, pandas 2.3.3, Python 3.13.

## 4. Results (seed 42, 8,192 records, 4,000 true people, 183 households)

| Method | Pair precision | Pair recall | Pair F1 | B-cubed F1 | Entities found | Largest cluster | False-merge pairs | Missed pairs |
|---|---|---|---|---|---|---|---|---|
| Rules + rapidfuzz | 0.952 | 0.913 | 0.932 | 0.971 | 4,278 | 9 | 267 | 510 |
| Splink, unsupervised, p ≥ 0.95 | 0.966 | 0.965 | 0.966 | 0.985 | 4,102 | 7 | 198 | 205 |
| recordlinkage + gradient boosting, supervised, p ≥ 0.9 | 0.976 | **0.975** | 0.975 | 0.990 | 4,082 | 7 | 142 | **145** |
| Splink + graph repair | 0.998 | 0.962 | 0.979 | 0.989 | 4,144 | 6 | 12 | 224 |
| ML + graph repair | **0.998** | 0.972 | **0.985** | **0.992** | 4,108 | 6 | **9** | 162 |

The blocking keeps 96.5% of true pairs and compares only 6,405 of the 33.5 million possible pairs.

**Graph repair.** 110 of Splink's 198 false-merge pairs are two people from the same household: same address, same surname and often a family email. Cannot-link constraints split 42 Splink clusters by cutting 80 edges, and false-merge pairs fall from 198 to 12 for a loss of 0.3 points of recall. The identifier graph flags 48 emails linked to more than one resolved person; 31 of them really are shared family mailboxes, and the rest point at missed matches a steward should look at.

**Mini MDM, incremental batch of 400 new records:** 198 were auto-linked to existing customers, 202 became new customers and 4 went to review. 197 of the 200 returning customers were attached correctly, and 1 was attached to the wrong customer.

**Customer spine:** 4,344 customers in 4,164 households (177 with more than one person). Household grouping finds 75% of the true same-household pairs at 97% precision. All 7 data contracts pass.

**Identity drift** between run 1 and a later snapshot (5% of records with new contact details, plus the 400 new records):

| Id strategy | Run-1 records whose id changed |
|---|---|
| Sequential numbering every run | 56.1% |
| Member record id as cluster id | 0.87% |
| Carry-forward by overlap, with aliases | **0.20%** |
| For context: records whose cluster really changed | 0.51% |

**MLOps, entity-disjoint test set:** logistic regression (v1) scores B-cubed F1 0.987 with ECE 0.012. Gradient boosting (v2) scores 0.993 with ECE 0.004, passes the gate and becomes champion. On the normal batch the score PSI is 0.03 and nothing alerts. On a simulated broken feed (phones missing, initials only) the score PSI is 2.77 and four alerts fire, while the match rate on its own looks *better* (0.98 against 0.89) because a third of the candidate pairs disappeared.

How to read the results:
- **Households break unsupervised matching.** Splink's EM learns that address + surname + email agreement is very strong evidence, so two people sharing a home and a mailbox look like one. This is the most common false merge in real customer data, and why "generic identifier" detection matters (we did this at Mars).
- **Constraints plus a graph fix it cheaply.** A min cut removes the cheapest set of edges between two records that cannot be the same person. Precision goes to 0.998 for both models. For customer data, precision matters most, because a false merge is a GDPR incident.
- **Supervised ML wins on recall, but it needs labels.** Here the labels come from the synthetic truth; in real life they come from data stewards reviewing the grey zone. Pairwise average precision is about 1.0, yet clusters still chain. **Always evaluate clusters, not only pairs.**
- **Hand-tuned rules are the weakest and the hardest to maintain**, although they are fully explainable. Use them for the deterministic tier (same email plus same DOB) and let a model do the rest.
- **Ids are a product.** A naive rebuild changes the id of over half the customers. Carry-forward keeps 99.8% stable and leaves an alias for every retired id.
- **Monitor several KPIs.** A broken feed can make a single KPI look better.

## 5. The approaches in one minute each

**Rules + fuzzy (rapidfuzz / fuzzywuzzy, jellyfish, Levenshtein, Jaro-Winkler).** You choose blocking keys, similarity functions, weights and thresholds by hand. It is fast and explainable, but every new source means re-tuning, and the weights are guesses.

**Splink (MoJ, MIT licence).** It uses the Fellegi-Sunter model:
- A **field** is one column compared between two records (surname, DOB, email...). Each field has a ladder of **comparison levels**: exact match, small typo, further apart, clearly different, missing. Every pair lands on one level per field.
- For each level it learns two numbers. `m` is the share of **true matches** that land on that level (67.6% of true matches have the same first name). `u` is the share of **different people** that land on it by coincidence (0.47% of random pairs share a first name).
- The level's **match weight** is `log2(m/u)` in bits: +7.2 for an exact first name, −3.2 for a clearly different one, 0 when the value is missing. The pair's total is the prior (−12.1 bits, because only 1 in 4,550 random pairs is a match) plus the weight of every field, converted to a probability with `2^w / (1 + 2^w)`.
- Worked examples with the demo's own trained numbers are in [DEMO_GUIDE.md section 3.5](DEMO_GUIDE.md#35-fellegi-sunter-step-by-step).
- `u` comes from random pairs and `m` from EM, so no labels are needed. Labels, when available, can estimate `m` or evaluate the model.
- Backends are DuckDB (laptop), Spark (Databricks), Athena and Postgres, so the same settings work everywhere.
- Explainability comes from waterfall charts.
- `predict_between` handles incremental matching, and the model is saved as JSON for versioning in MLflow.

**Graph resolution (networkx, GraphFrames on Spark, Neo4j / TigerGraph in production).** Records are nodes, accepted matches are weighted edges and a customer is a connected component. Graph methods catch what pair scores miss: chaining through one bad edge, identifiers shared by many people, and household or company hierarchies. Cannot-link constraints plus a minimum cut are a simple, explainable repair; community detection (Louvain, Leiden) and correlation clustering are the next options for very large components.

**Zingg (AGPL community / commercial enterprise).** It is ML-first with active learning:
- It shows you the most uncertain pairs, and you label about 30–40 matches.
- It then learns both the blocking functions and the classifier.
- It runs on Spark and on Databricks, and has incremental runs.
- Choose it when the data is messy and you can afford a labelling session.
- Watch the AGPL licence if the code is distributed.

**Supervised classifier (recordlinkage + scikit-learn / XGBoost).** You build your own features and model. It is the most flexible, since you can add embeddings, LLM features or any business signal, but it needs labelled pairs and MLOps around it.
- Labels are pairs marked "same person" or "not", not features. They come from steward decisions on the review queue, a golden set, silver labels from identifiers the business already trusts (national ID, loyalty card, shared login), and active learning. Synthetic data like this demo's is for building and testing, not for training a production model. See [DEMO_GUIDE.md section 3.6, Step 7](DEMO_GUIDE.md#step-7-where-it-fails-and-where-labels-come-from).

**Precision or recall?** For customer identity usually precision: a false merge exposes one person's data to another and is hard to undo, while a missed match is a duplicate that a later run or a steward can link. Recall wins for fraud, AML, sanctions screening and GDPR access requests. Use two thresholds (auto-merge, review queue, keep apart) and measure on clusters. See [DEMO_GUIDE.md section 3.9](DEMO_GUIDE.md#precision-or-recall-which-matters-more).

**Licences.** Nothing in the demo needs a paid licence. Splink is MIT. Zingg Community is AGPL-3.0 (free; obligations only if you modify and distribute it or offer it as a service), and Zingg Enterprise is a paid edition. rapidfuzz, recordlinkage, networkx, DuckDB and scikit-learn are MIT or BSD. Commercial alternatives: Senzing, Informatica, Reltio, Tamr, Quantexa.

**Others worth naming:**
- `dedupe` (Python, active learning, BSD).
- Senzing (commercial, entity resolution as an engine, real-time).
- Databricks ARC (an automated Splink wrapper).
- Embeddings plus vector search (Databricks Vector Search, FAISS) as a blocking rule for very messy text.
- LLM-as-judge, only on the grey zone and never on every pair, because of cost and PII.
- Commercial MDM tools (Informatica MDM, Reltio, Tamr, Profisee, Semarchy) when the business wants a steward UI and workflow out of the box.

## 6. The mini MDM and the customer spine: what they do and why

Matching gives you clusters. MDM turns clusters into a **governed customer master** that downstream systems can trust, and the spine is the thin table everyone joins to.

| Concept | In the demo | Production on Databricks |
|---|---|---|
| Stable master id | `customer_id` from a DuckDB sequence; stable for the database lifetime (the demo's full run resets the database) | Identity table in Delta, never regenerated |
| Id carry-forward | `07_identity_drift.py`: overlap matching, split and merge events, `id_alias.csv` | Same logic as a MERGE on the identity table, aliases in Delta |
| Crosswalk | `xref(source_record_id → customer_id, probability, method)` | Delta table consumed by CRM, billing and analytics |
| Survivorship | Names and DOB: most frequent value, then source priority (CRM > BILLING > WEB). Contact data: most recent. | Same rules in Spark SQL, configured per field in a table |
| Provenance | JSON per golden record: which source and which rule won each field | Same, plus Unity Catalog lineage |
| History | `golden_history` with `valid_to` (SCD2) | Delta SCD2 / Change Data Feed |
| Identity hierarchy | `identity_hierarchy(node_id, node_type, parent_id, rule, confidence)`: household → customer → source | Same table; households can also come from a graph job (GraphFrames) |
| Customer spine / Golden Layer | `customer_spine`: one row per customer with household, golden attributes, source keys, weakest-link probability, model version | Gold Delta table in Unity Catalog, the only customer table downstream teams use |
| Governance | `column_classification` for PII, 7 data contracts that stop the publish | UC tags and column masks, DLT expectations or Lakeflow data quality rules |
| Grey zone | `review_queue` with p between 0.5 and 0.95; the record becomes a new customer until a steward decides | Databricks App or Streamlit for stewards; their decisions become training and evaluation labels |
| Steward actions | `approve_review`, `reject_review`, `unmerge_record` with a reason in `steward_audit` | Same, with an audit trail |
| Incremental | New records scored only against existing ones with the **saved** Splink model (`predict_between`) | Workflow task on Change Data Feed |
| GDPR erasure | `erase_customer` removes source records, crosswalk, golden record and history | Same, plus Delta `VACUUM` and UC column masks on PII |

Still not covered: re-clustering customers already in the master after a steward merge, company (B2B) hierarchies, and a steward UI.

## 7. How this maps to Databricks

1. **Bronze:** one Delta table per source, loaded with Auto Loader or Lakeflow.
2. **Silver:** `customer_std`, with the same standardisation as `common/standardise.py`.
3. **Matching job:** Splink on `SparkAPI` (`databricks/splink_on_databricks.py`) writes `pairs`, `clusters` and `review_queue` to Unity Catalog.
4. **Graph job:** cannot-link repair and household components with GraphFrames, writing repaired clusters and `shared_identifiers`.
5. **MDM job:** survivorship builds `golden_record`, `xref` and `golden_history`; ids are carried forward, never regenerated.
6. **Gold / Golden Layer:** `customer_spine` and `identity_hierarchy`, published only when the data contracts pass.
7. **Incremental:** Change Data Feed on silver, then `predict_between`, then attach, create or review.
8. **Feature store:** standardised attributes and pair features as Unity Catalog feature tables keyed by `unique_id` and `(id_l, id_r)`, so training and incremental scoring use the same features.
9. **MLflow:**
   - Log the model, the parameters and the feature-set version.
   - Log the unlabelled KPIs every run: entities, max cluster size, review queue size, match rate per source, score PSI and id drift.
   - Once stewards have labelled pairs, also log pairwise and B-cubed precision/recall and calibration against the golden set.
   - Promote a new model to the `champion` alias only when it passes the gate.
10. **Asset Bundle** for dev/test/prod, and **Workflows** for scheduling.

## 8. Ten-minute walkthrough

1. **(1 min)** "Three systems, 8k records, 4k real people, 183 households. I generated them so I know the truth and can measure quality, which you never can in production."
2. **(1 min)** Rules + rapidfuzz: "The classic approach most teams start with: blocking, weighted fuzzy scoring, thresholds, Union-Find. F1 is 0.93."
3. **(2 min)** Splink: "Same blocking, but the weights are learned with EM and no labels." Open the waterfall chart: "This is how I explain a match to a data steward." Then: "Precision is only 0.966, and over half the false merges are households."
4. **(1 min)** ML: "With labels from stewards, a classifier gets the best recall. Pairwise AP is 1.0 and clusters still chain, so I evaluate at cluster level, with B-cubed."
5. **(2 min)** Graph: "A customer is a connected component. Two records with different DOBs cannot be the same person, so I cut the cheapest edges between them. False merges go from 198 to 12. The identifier graph gives the steward the shared-mailbox list."
6. **(1 min)** MDM and spine: "Clusters become a governed master: survivorship with provenance, crosswalk, history, a household → customer → source hierarchy, and a spine table that is only published when its contracts pass."
7. **(1 min)** Drift and MLOps: "A naive rebuild changes 56% of ids; carry-forward changes 0.2%. The model has a registry, a promotion gate and PSI monitoring; a broken feed fires four alerts while the match rate looks better."
8. **(1 min)** Close: "For a real platform I'd start with Splink on Spark plus graph constraints, add the steward loop for labels, and only add an ML layer where the grey zone is big."

## 9. Honest limits

- **Synthetic data is cleaner than real data.** Real data has company records mixed with people, transliterated names, junk values like `test@test.com` and much larger households. Expect lower numbers.
- **Some Splink levels are untrained.** Splink warns that a few `dob` and `postcode` levels stay untrained, because the generator never produces near-miss DOBs or same-sector postcodes. Real data trains them.
- **The cannot-link rules are simple.** They trust the DOB. In real data a wrong DOB on one source would split a real person; weigh the rule by source quality.
- **Households use any address a customer ever had.** That finds more households but would also link a person to a previous occupant of their home. Production would use only current or recent addresses.
- **Zingg and the Databricks notebook were not executed here.** Check them against the installed versions before showing them live.
- **The MDM, spine and registry are teaching models, not products.** No concurrency control, steward UI or access control; the registry is a JSON file.

## 10. Files after a run

`results/comparison.md`, `metrics_*.csv`, `clusters_*.csv`, `pairs_splink.csv`, `review_queue_*.csv`, `splink_model.json`, `splink_*.html`, `splink_threshold_sweep.csv`, `pairs_ml_features.csv`, `shared_identifiers.csv`, `mdm.duckdb`, `mdm_golden_record.csv`, `mdm_xref.csv`, `mdm_review_queue.csv`, `customer_spine.csv`, `identity_hierarchy.csv`, `spine_contracts.csv`, `identity_drift.csv`, `id_alias.csv`, `id_events.csv`, `feature_store.duckdb`, `model_registry/`, `model_versions.csv`, `monitoring_report.csv`.
