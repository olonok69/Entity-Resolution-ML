# Customer Matching Demo Guide

This guide is the runbook for presenting the laptop demo. It uses synthetic data with known entity IDs; results are useful for comparing approaches, not as production performance claims.

## Before the call

Run these commands from PowerShell in the repository's `er-demo/` directory. They use the virtual environment's interpreter directly, so activation is not required.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe data/generate_data.py
.\.venv\Scripts\python.exe 01_rules_rapidfuzz.py
.\.venv\Scripts\python.exe 02_splink.py
.\.venv\Scripts\python.exe 03_ml_recordlinkage.py
.\.venv\Scripts\python.exe 04_mdm.py
.\.venv\Scripts\python.exe 05_compare.py
```

The sequence is the same as `run_all.sh`, written out so it works in PowerShell without Bash. Run it before the call: the matching stages can take longer than the README's approximate 30 seconds on a cold or slower machine. `04_mdm.py` deletes and recreates `results/mdm.duckdb`; running the sequence again resets the MDM state and regenerates its exports.

Check that these files exist before presenting:

- `results/comparison.md` and the `metrics_*.csv` summaries.
- `results/splink_match_weights.html` and `results/splink_waterfall_example.html`.
- `results/mdm.duckdb`, `results/mdm_golden_record.csv`, `results/mdm_xref.csv`, and `results/mdm_review_queue.csv`.

Open the two Splink HTML charts in a browser before screen sharing. The demo is local; Zingg and the Databricks SparkAPI example are not part of the laptop run.

## Code tour: end-to-end flow

The pipeline compares three matching strategies over the same generated records, then uses Splink's clusters as the starting point for a small master-data workflow:

```text
data/generate_data.py
  |  customers.csv + new_batch.csv; true_entity_id is evaluation truth
  v
common/standardise.py
  |  cleaned names, contact fields, phonetic codes, unique_id
  +----------------------+----------------------+
  v                      v                      v
01_rules_rapidfuzz.py    02_splink.py         03_ml_recordlinkage.py
 rules + fuzzy score     EM probabilities     supervised pair model
  |                      |                      |
  +---------- clusters + metrics ---------------+
             |
             v
       04_mdm.py
       customer master + incremental batch
             |
             v
       05_compare.py
```

All three matchers use blocking to avoid testing every possible pair. Their scores are not interchangeable: the rules script produces a hand-weighted similarity score; Splink produces a probability from learned Fellegi-Sunter parameters; the ML script produces a classifier probability trained on synthetic truth. The thresholds in each script are therefore separate operating choices, not a shared calibration.

## Code tour: each script

### 0. Generate the experiment: [data/generate_data.py](data/generate_data.py)

**Purpose:** make known-truth data so match quality can be measured reproducibly. `SEED`, `N_ENTITIES`, and `N_NEW_BATCH` set the experiment size and reproducibility. `make_entity()` creates the clean person-level truth; `noisy_copy()` generates source-specific records with realistic variations; `main()` creates the multi-source population and a later arrival batch.

**What gets written:** `data/customers.csv` is the initial population and `data/new_batch.csv` is the incremental feed. `true_entity_id` is the answer key used by evaluation; it must not be treated as a matching feature in a real system. The Splink and ML scripts carry it through for synthetic evaluation or label creation, but do not declare it as a blocking key or comparison feature.

**Why it matters:** without a known answer key, a demo can show plausible matches but cannot calculate false merges and missed links. The deterministic seed makes runs comparable, although Faker or library version changes can affect exact outputs.

### Shared foundation: [common/standardise.py](common/standardise.py)

**Purpose:** apply identical cleaning before candidate generation and comparison. `standardise()` copies the input, maps `source_record_id` to Splink's `unique_id`, then adds normalized names, nickname canonicalization, email, phone, postcode, address, DOB, and metaphone fields. The smaller `clean_*` functions implement each field rule.

**Connection to the matchers:** `01_rules_rapidfuzz.py` and `02_splink.py` call `standardise(raw)` directly. `03_ml_recordlinkage.py` calls it before feature construction. `04_mdm.py` uses it both when loading source rows and when preparing records for incremental Splink scoring. The MDM stores cleaned golden-record attributes while retaining original source record IDs and source systems.

**Design point:** normalization makes formatting differences less informative, while fuzzy comparison handles remaining misspellings and variations. Production standardisation needs explicit locale, validation, and source-specific policies; these helpers are intentionally small teaching examples.

### Shared evaluation: [common/evaluate.py](common/evaluate.py)

**Purpose:** score predicted clusters against `true_entity_id`, not just inspect sample pairs. `evaluate_clusters()` calculates pairwise precision/recall/F1, B-cubed metrics, entity counts, largest cluster, false-merge pairs, and missed pairs. `_pairs()` creates pair sets used for pairwise comparisons. `blocking_recall()` measures candidate pair completeness and reduction ratio. `union_find_clusters()` turns accepted pair edges into connected components.

**Connection to the matchers:** the rules and supervised scripts call `union_find_clusters()` because their thresholds produce edges. Splink uses its own clustering implementation. All three use `evaluate_clusters()` so the reported cluster metrics share a definition; only the candidate-pair script additionally reports blocking recall.

**Interpretation:** pair metrics judge co-clustered pairs; B-cubed averages quality per record and avoids allowing large clusters to dominate. `largest_cluster` is a useful chaining warning, not a quality metric by itself.

### 1. Hand-built matcher: [01_rules_rapidfuzz.py](01_rules_rapidfuzz.py)

**Input:** `data/customers.csv`. **Output:** `results/clusters_rapidfuzz.csv`, `results/review_queue_rapidfuzz.csv`, and `results/metrics_rapidfuzz.csv`.

1. `BLOCKING_KEYS` lists alternative field combinations. `candidate_pairs()` groups records by each key and unions the resulting pairs. Blocks over 200 records are skipped to avoid explosive comparisons from shared values such as generic contact details.
2. `score()` builds field-level similarities. `sim()` uses RapidFuzz for strings; exact values such as DOB and phone use exact agreement. Missing values are omitted and the remaining weights are renormalized.
3. `AUTO_MATCH` and `REVIEW` split scores into automatic edges, a review list, and rejected candidates.
4. `union_find_clusters()` converts auto-match edges into connected components; `evaluate_clusters()` compares these groups with truth.
5. `main()` writes the cluster assignments, review pairs, and one-row metric summary.

**What to explain:** this is transparent because the team chose the fields, weights, blocking rules, and thresholds. It is also brittle: changes in source quality can require hand-retuning, and one erroneous edge can join otherwise separate components.

### 2. Probabilistic matcher: [02_splink.py](02_splink.py)

**Input:** `data/customers.csv`. **Outputs:** `results/splink_model.json`, `pairs_splink.csv`, `clusters_splink.csv`, `review_queue_splink.csv`, `splink_threshold_sweep.csv`, three HTML charts, and `metrics_splink.csv`.

1. `settings` declares the dedupe task, unique record ID, candidate-generation blocks, and field comparisons. Term-frequency adjustments reduce the weight of common names compared with rare names.
2. `build_linker()` registers the standardized data with DuckDB and creates the Splink `Linker`.
3. `train()` estimates the prior match probability, estimates non-match agreement (`u`) using random pairs, and uses expectation-maximisation on multiple blocks to estimate match agreement (`m`). No labels are supplied to training.
4. In `main()`, `predict()` scores candidate pairs; the low prediction threshold preserves candidates for later threshold decisions. Splink clusters at `CLUSTER_THRESHOLD`, which is 0.95.
5. The threshold sweep shows how quality changes as the cluster threshold changes. The saved JSON is the trained model used by incremental scoring. The match-weights and m/u charts explain model parameters; the waterfall chart explains one selected pair's field contributions.

**Connection to MDM:** `04_mdm.py` loads the saved JSON model and uses `predict_between()` to compare the new batch with the existing master. That is why the generated model and trained Splink version are prerequisites for the MDM stage.

### 3. Supervised matcher: [03_ml_recordlinkage.py](03_ml_recordlinkage.py)

**Input:** `data/customers.csv`. **Outputs:** `results/pairs_ml_features.csv` and `results/metrics_ml.csv`.

1. The script imports the blocking function from `01_rules_rapidfuzz.py`, so the supervised model learns to score the candidate pairs that pass those same blocks; it does not compare every possible pair.
2. `features()` calculates name similarities, phonetic equality, exact date/contact/postcode agreement, and a character n-gram TF-IDF cosine similarity over joined record text.
3. `main()` creates binary labels by comparing the pair's `true_entity_id` values. These labels are available only because the data is synthetic.
4. The two-fold cross-fitting split is based on the left record's entity ID: pairs whose left record belongs to a fold are scored by the model trained on the other fold. This is out-of-fold by the left-side grouping, but it is not a strict entity-disjoint split because an entity can still appear on the right side of training pairs. The classifier's average precision is reported as a pair-ranking metric.
5. The script thresholds those pair probabilities, forms connected components, evaluates clusters, and writes features with labels and out-of-fold probabilities for inspection.

**What to explain:** the feature/model approach is flexible and can learn combinations that are awkward to hand-code, but these results use known synthetic truth. A production evaluation should use a strict entity-disjoint split, plus steward labels, calibration, monitoring, and a review process. The script's AP is pair-level; the cluster metrics expose transitive chaining.

### 4. Master-data workflow: [04_mdm.py](04_mdm.py)

**Inputs:** raw initial data, `results/clusters_splink.csv`, `results/splink_model.json`, and `data/new_batch.csv`. **Outputs:** `results/mdm.duckdb` plus golden-record, crosswalk, and review-queue CSV exports.

1. `MiniMDM.__init__()` creates the source, crosswalk (`xref`), current golden record, history, review, and audit tables in DuckDB.
2. `initial_load()` writes the source rows, maps each Splink cluster to a generated `customer_id`, populates `xref`, and calls `rebuild_golden()`.
3. `survive()` chooses one winning non-empty value per field. Names and DOB use frequency, then source priority, then recency; contact fields use recency, then source priority. The JSON `provenance` records the source record and rule that won each field.
4. `rebuild_golden()` recomputes only touched customers, closes the previous open history version, increments the version, and inserts the new snapshot. A customer with no remaining source records has no current golden row.
5. `score_new_records()` constructs a Splink linker from the saved model and scores existing records against the new batch without retraining. `incremental_load()` chooses the best candidate per new record: at or above 0.95 it attaches automatically; otherwise it creates a new customer, and scores at or above 0.50 enter review.
6. `approve_review()` moves all members of the temporary new customer to the candidate customer and rebuilds both records; `reject_review()` leaves the new customer in place and marks the review decision.
7. `unmerge_record()` moves one source row to a new customer after validating a reason and that the original customer has another member. It updates the crosswalk and review status, records the action in `steward_audit`, and rebuilds both golden records inside a transaction.
8. `erase_customer()` removes the customer's source rows, crosswalk, master, and history. The demo's `main()` exercises an approval and an erasure, prints incremental correctness using truth for evaluation only, then exports CSVs.

**Important distinction:** the normal script does not run `unmerge_record()`; the optional snippet later in this guide is a separate, state-changing exercise. Customer IDs are stable within this database's lifecycle, but `main()` deletes and recreates the DuckDB file at startup, so the full demo run is deliberately not a persistent production identity service.

### 5. Comparison report: [05_compare.py](05_compare.py)

**Inputs:** the three `metrics_*.csv` outputs. **Output:** `results/comparison.md`.

The script concatenates whichever metric files exist, selects the shared comparison columns, renders a Markdown table, writes it, and prints it. It does not run matchers or recalculate scores. Run it after the three matching scripts; an absent metrics file means a method is omitted rather than rerun automatically.

### Optional integrations: [databricks/splink_on_databricks.py](databricks/splink_on_databricks.py) and [zingg/zingg_customers.py](zingg/zingg_customers.py)

`databricks/splink_on_databricks.py` translates the local Splink path to SparkAPI, Delta tables in Unity Catalog, and MLflow logging. The notebook expects a Databricks-provided `spark` session, pre-existing Silver table, catalog/schema, checkpoint volume, and an installed compatible Splink environment. It writes pairs, clusters, review queue, and a JSON model artifact. It is a design example, not part of the verified laptop pipeline; MDM survivorship and incremental work are listed there as downstream tasks.

`zingg/zingg_customers.py` describes a separate active-learning workflow on Spark. Its phase argument selects `findTrainingData`, `label`, `train`, or `match`; `FieldDefinition` controls which fields are ignored, exact, or fuzzy. It expects the Zingg runtime/jar and its input/output paths. The Python API and field names must be checked against the installed Zingg version before execution. It does not feed the local comparison report.

## Ten-minute walkthrough

| Time | Show | Explain |
|---|---|---|
| 1 min | `data/customers.csv` and the comparison summary | Three source systems contain 8,149 records for 4,000 generated people. Because the generator preserves truth, this demo can measure errors that production data usually cannot label completely. |
| 2 min | `01_rules_rapidfuzz.py` results | Blocking avoids all-pairs comparison; weighted fuzzy scores decide auto-match, review, or no-match. The approach is explainable, but hand-tuned and vulnerable to transitive chaining. |
| 3 min | Splink metrics and `splink_waterfall_example.html` | Splink learns Fellegi-Sunter weights with EM and no labels. Use the waterfall to show which field agreements raise or lower a pair's match weight. On this seed, precision is 0.993 at the documented threshold. |
| 1 min | `03_ml_recordlinkage.py` results | Supervised learning improves recall here because synthetic truth supplies labels. In production, steward-reviewed pairs would provide labels; assess clusters as well as pairs because one bad edge can chain records. |
| 2 min | `04_mdm.py` output and MDM tables | Incremental records are scored against the existing master. Show stable customer IDs, survivorship/provenance, crosswalk, SCD2 history, review decisions, and erasure. The printed counts and CSVs are the evidence. |
| 1 min | Databricks mapping in `README.md` | Describe how the laptop shape maps to Bronze/Silver/Gold, SparkAPI, Delta, Unity Catalog, Workflows, and MLflow. Be clear that this workspace did not execute the Databricks or Zingg integrations. |

Use `results/comparison.md` as the source for exact metrics. The documented values depend on the fixed data seed and package versions; do not imply they are expected production metrics.

## Optional: demonstrate un-merge

The normal `04_mdm.py` run does not call `unmerge_record`; it does run an approval and erasure example. To demonstrate un-merge, run this optional snippet from PowerShell after the demo run. It changes `results/mdm.duckdb` and does not refresh the CSV exports. Re-run the pipeline to restore the original demo state.

```powershell
@'
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("mdm_demo", "04_mdm.py")
mdm_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mdm_demo)

mdm = mdm_demo.MiniMDM(Path("results/mdm.duckdb"))
source_record_id = mdm.con.execute("""
    SELECT x.source_record_id
    FROM xref x
    JOIN (SELECT customer_id FROM xref GROUP BY customer_id HAVING count(*) > 1) multi
      USING (customer_id)
    LIMIT 1
""").fetchone()[0]
new_customer_id = mdm.unmerge_record(source_record_id, "Demo: correcting a false merge")
print("unmerged", source_record_id, "to", new_customer_id)
print(mdm.con.execute("SELECT * FROM steward_audit ORDER BY acted_at DESC LIMIT 1").df())
mdm.con.close()
'@ | .\.venv\Scripts\python.exe -
```

Explain that the source row is assigned a new customer ID, the old and new golden records are rebuilt, history is versioned, and the steward reason is written to `steward_audit`. This is a single-record correction, not general cluster splitting or full re-clustering.

## Questions to expect

- **Why not match every pair?** There are 33 million possible pairs; blocking retains 96.8% of true pairs while evaluating about 6,200 candidates.
- **Why favor precision?** A false merge can expose one person's data to another. Keep uncertain records in the review queue rather than silently joining them.
- **Why show cluster metrics?** Pair precision alone hides chaining. B-cubed and largest-cluster size reveal cluster-level effects.
- **What is not production-ready?** The MDM is a teaching model: no concurrent write handling, steward UI, general cluster-split workflow, or production access controls. Synthetic data is cleaner than real customer data.

## Troubleshooting

- If an output is missing, rerun the steps above in order; later stages consume earlier CSVs and the saved Splink model.
- If PowerShell cannot find `python`, install Python 3.13 or use the Python launcher to create the virtual environment, then continue with `.venv`'s interpreter.
- If a Splink chart does not open, use the browser's Open File action and select it from `results/`.
- The Databricks and Zingg examples require their respective Spark/Databricks or Zingg runtime and are not validated by the local run.