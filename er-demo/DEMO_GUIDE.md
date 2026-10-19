# Customer Identity Resolution Demo Guide

This guide has three jobs:

1. **Runbook** for presenting the laptop demo live (sections 1, 5, 6).
2. **Study notes** for the interview: the concepts behind each step, the maths you may be asked to explain, and the questions to expect with answers (sections 2, 3, 7, 8, 9).
3. **Source for the YouTube video.** The recording script with chapters and timings is in [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md); it follows the same order as the code tour here.

The demo uses synthetic data with known entity and household IDs. Results are useful for comparing approaches, not as production performance claims.

## Contents

1. [Before the call](#1-before-the-call)
2. [What the role asks for, and where the demo shows it](#2-what-the-role-asks-for-and-where-the-demo-shows-it)
3. [Concepts primer](#3-concepts-primer)
4. [Code tour](#4-code-tour)
5. [Ten-minute walkthrough](#5-ten-minute-walkthrough)
6. [Optional: demonstrate un-merge](#6-optional-demonstrate-un-merge)
7. [System design: the framework at scale](#7-system-design-the-framework-at-scale)
8. [Questions to expect](#8-questions-to-expect)
9. [Your own stories](#9-your-own-stories)
10. [Glossary](#10-glossary)
11. [Troubleshooting](#11-troubleshooting)

## 1. Before the call

Run these commands from PowerShell in the repository's `er-demo/` directory. They use the virtual environment's interpreter directly, so activation is not required.

```powershell
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

The sequence is the same as `run_all.sh`, written out so it works in PowerShell without Bash. Run it before the call: the full run takes about 45 seconds on a laptop and longer on a cold machine. `05_mdm.py` deletes and recreates `results/mdm.duckdb`, and `08_mlops_feature_store.py` resets the feature store and the model registry, so running the sequence again always gives the same starting state.

Check that these files exist before presenting:

- `results/comparison.md`: every metric table in one place. Keep it open in a tab.
- `results/splink_match_weights.html` and `results/splink_waterfall_example.html`: open both in a browser before screen sharing.
- `results/mdm.duckdb` (golden record, crosswalk, history, spine, hierarchy) and `results/feature_store.duckdb`.
- `results/shared_identifiers.csv`, `results/identity_drift.csv`, `results/monitoring_report.csv`, `results/model_registry/registry.json`.

Optional: `pip install mlflow` before the run and `08_mlops_feature_store.py` also logs both model versions to `results/mlruns`; `mlflow ui --backend-store-uri results/mlruns` then shows them. The demo works without it.

The demo is local. Zingg and the Databricks SparkAPI example are not part of the laptop run.

## 2. What the role asks for, and where the demo shows it

Use this table to steer the conversation: when they ask about a requirement, name the file and the number.

| Requirement in the job description | Demo evidence | The number to quote |
|---|---|---|
| Graph-based techniques and entity resolution | `04_graph_resolution.py`, households in `06_customer_spine.py` | False-merge pairs 198 → 12 after min-cut repair |
| Record linkage and fuzzy matching | `01`, `02`, `common/standardise.py` | Blocking keeps 96.5% of true pairs with 0.02% of comparisons |
| ML where deterministic rules are insufficient | `02` (EM, no labels), `03` (supervised), Zingg | Rules F1 0.93 → ML F1 0.975 |
| Customer-spine architecture, governed identity hierarchy | `06_customer_spine.py` | 7 data contracts, household → customer → source |
| Reusable framework, less duplication, less identity drift | `common/`, saved model reused 3 times, `07_identity_drift.py` | Id drift 56% → 0.2% |
| Matching-quality metrics: accuracy, confidence, performance | `common/evaluate.py`, threshold sweep, `08` calibration | B-cubed F1, ECE 0.004 |
| Integration into data platforms and the Golden Layer | `05_mdm.py`, `06` spine, `databricks/` | `customer_spine` table, Bronze/Silver/Gold mapping |
| MLOps: deployment, monitoring, lifecycle | `08_mlops_feature_store.py`, `databricks/` MLflow | Gate promotes v2; broken feed fires 4 PSI alerts |
| Feature stores | `08_mlops_feature_store.py` | Versioned features, serving refuses a different version |
| Customer master data and MDM | `05_mdm.py` | 197/200 returning customers attached correctly |
| Collaboration with stakeholders | Review queue, waterfall chart, steward audit, shared-identifier list | "The waterfall is how I explain a match to a steward" |

## 3. Concepts primer

Read this section once end to end before the interview; each part is what you would say if asked "explain X".

### 3.1 The problem

**Entity resolution (ER)** finds records that refer to the same real-world thing. For customers it has three flavours: **deduplication** (one table), **record linkage** (across tables), and **canonicalisation** (choosing the best values). Customer data has no shared key between systems, so we infer identity from noisy attributes: names, DOB, email, phone, address.

The pipeline is always the same shape:

```text
standardise -> block -> compare -> score -> classify (threshold) -> cluster -> master (golden record) -> publish (spine)
```

Most quality comes from the first and the last steps people forget: standardisation, and evaluating clusters rather than pairs.

### 3.2 Standardisation

Make formatting differences disappear before comparing: case, accents, titles (`Mr`), nicknames (`Bob` → `robert`), phone formats (`+44 7…` → `07…`), postcode spacing, Gmail dots and plus-tags. Phonetic codes (Soundex, Metaphone) let `Smith` and `Smyth` share a block. Rule of thumb: normalise what is formatting, compare fuzzily what is a real difference.

### 3.3 Blocking (indexing)

Comparing every pair is `n(n-1)/2`: 33.5 million pairs for 8,192 records, 5 × 10¹⁴ for 30 million. Blocking only compares records that share a cheap key (same email, same DOB + surname sound, same postcode + first-name sound). Several blocking rules are unioned, so a record missed by one rule is caught by another.

- **Pair completeness (blocking recall)** = true pairs that survive blocking / all true pairs. This is a ceiling on recall: no model can match a pair it never sees. Here 96.5%.
- **Reduction ratio** = 1 − candidates / all pairs. Here 99.98%.
- Very large blocks (a shared generic email) are skipped or capped, otherwise one value creates millions of comparisons.
- Other methods: sorted neighbourhood, canopy clustering, LSH / MinHash, and embedding nearest-neighbour search for messy text.

### 3.4 Comparing and scoring

Each field gets a similarity: exact, Levenshtein (edit distance), Jaro-Winkler (good for short names, rewards a common prefix), token-set ratio (word order), q-gram / TF-IDF cosine (long text), date tolerance. Then three families of scoring:

| Family | How the score is built | Labels needed | Strength | Weakness |
|---|---|---|---|---|
| Deterministic rules | `same email AND same DOB` | No | Exact, auditable | Misses everything noisy |
| Weighted fuzzy score | Hand-picked weights × similarities | No | Explainable, fast | Weights are guesses, re-tune per source |
| Probabilistic (Fellegi-Sunter) | Learned `m` and `u` per field level | No (EM) | Principled weights, explainable | Assumes field independence |
| Supervised classifier | Model on pair features | Yes | Most flexible, learns interactions | Needs labels and MLOps |
| Active learning (Zingg, dedupe) | Classifier trained on the pairs it is least sure about | A few dozen | Few labels | Labelling session, licensing |

### 3.5 Fellegi-Sunter, worked example

For each field and agreement level the model has two probabilities:

- `m = P(level | records match)`, e.g. surnames agree exactly for 95% of true matches (typos make up the rest).
- `u = P(level | records do not match)`, e.g. surnames agree for 1% of random pairs (common names).

The **match weight** of an observed level is `log2(m / u)`. Agreement on a rare value is strong evidence, agreement on a common one is weak; disagreement gives a negative weight. Weights add up because the model assumes the fields are independent given match status. A **prior** weight comes from `λ`, the probability that two random records match.

Illustrative numbers (not the trained model's):

| Evidence | m | u | Weight log2(m/u) |
|---|---|---|---|
| Prior: λ ≈ 5,800 true pairs / 33.5M pairs ≈ 0.00017 | | | log2(λ / (1 − λ)) ≈ −12.5 |
| First name agrees | 0.90 | 0.02 | +5.5 |
| Surname agrees | 0.95 | 0.01 | +6.6 |
| DOB agrees | 0.92 | 0.0003 | +11.6 |
| Email missing | | | 0 (null levels add nothing) |
| Postcode disagrees | 0.25 | 0.99 | −2.0 |
| **Total** | | | **+9.2** |

Probability = `2^w / (1 + 2^w)` = 2^9.2 / (1 + 2^9.2) ≈ 0.998. The waterfall chart in `results/splink_waterfall_example.html` draws exactly this sum for one real pair.

- **`u` estimation:** sample random pairs; almost all are non-matches, so the agreement rates in them are `u`.
- **`m` estimation with EM, no labels:** start with guesses, compute each pair's match probability (E step), re-estimate `m` from those probabilities (M step), repeat until stable. Each EM run blocks on one field (e.g. DOB) and so cannot learn that field's `m`; that is why `02_splink.py` runs EM on three different blocks.
- **Term-frequency adjustment:** agreement on `smith` gets less weight than agreement on `featherstonehaugh`, using the value's own frequency instead of the field average.

### 3.6 Supervised matching

Labels are pairs marked match / non-match, usually from stewards reviewing the grey zone. Features are field similarities plus anything useful (phonetic equality, whole-record TF-IDF, embeddings). Pitfalls you should name:

- **Leakage:** a person appears in many pairs, so a random pair split leaks identity. Split **by entity** (`08` uses a strict entity-disjoint split; `03` uses a cheaper left-record fold).
- **Class imbalance:** after blocking positives are common, before blocking they are rare. Report average precision, not accuracy.
- **Calibration:** a threshold of 0.9 only means something if p = 0.9 is right 90% of the time. Measure with Brier score and ECE (section 3.9).

### 3.7 Clustering and the graph view

Matching produces pairs; customers are **clusters**. The usual step is transitive closure: connected components (Union-Find). Matching is not transitive in truth (A≈B and B≈C does not prove A≈C), so one bad edge merges two people: **chaining**. Graph techniques address this:

- **Cannot-link constraints:** business rules that say two records are different people (conflicting DOB, clearly different first name with no matching DOB). `04_graph_resolution.py` finds components that contain such a pair.
- **Minimum cut:** with edge capacities = match probability, the min cut is the cheapest set of edges whose removal separates the two conflicting records. It cuts the weak bridge, not the strong core.
- **Other options:** cluster density checks, edge betweenness, community detection (Louvain, Leiden), correlation clustering, and Splink's own threshold-based clustering.
- **Identifier graph:** a bipartite graph of records and identifiers (emails, phones). An email linked to several resolved people is a **shared or generic identifier** (a family mailbox, `info@company.com`, `test@test.com`) and should be down-weighted or excluded from blocking. Here 31 of 48 flagged emails are real family mailboxes; the rest point at missed matches.
- **Hierarchies are graphs too:** households are connected components of a customer-address graph.

### 3.8 MDM, golden record and customer spine

- **Golden record:** one best version of each customer, built with **survivorship** rules per field: most frequent, most recent, most trusted source, most complete. Keep **provenance** (which record and which rule won), so every value can be explained.
- **Crosswalk (xref):** source system + source id → master id. Downstream systems use it to translate their own ids.
- **MDM styles:** registry (only the crosswalk is central), consolidation (golden record built centrally for analytics), coexistence (golden record synced back to sources), centralised (the hub is the system of entry). This demo is consolidation style.
- **Data stewardship:** grey-zone review, approve / reject / un-merge with a reason and an audit trail. Steward decisions become labels.
- **Customer spine:** the thin, governed table every domain joins to: one row per customer with the stable key, its place in the hierarchy, the source keys, and quality metadata (model version, weakest link). In a medallion lakehouse it sits in Gold, the "Golden Layer".
- **Identity hierarchy:** levels such as source record → customer → household (→ company / group for B2B). Each edge stores the rule and confidence that created it.
- **Governance:** PII classification, data contracts (assertions that must hold before publishing), lineage, access control, GDPR erasure across every table.

### 3.9 Matching-quality metrics

Truth: `T(r)` is the true cluster of record `r`, `C(r)` the predicted one.

- **Pairwise precision** = correctly co-clustered pairs / predicted co-clustered pairs. **Recall** = correctly co-clustered pairs / true co-clustered pairs. Large clusters dominate because pairs grow quadratically.
- **B-cubed:** per record, precision `|C(r) ∩ T(r)| / |C(r)|` and recall `|C(r) ∩ T(r)| / |T(r)|`, averaged over records. Every record counts once.
- **False-merge pairs vs missed pairs:** for customer data a false merge is worse (privacy, wrong marketing consent), so operate at high precision and send the grey zone to review.
- **Confidence and calibration:** Brier score = mean (p − y)². **ECE** = Σ over probability bins of (bin share × |observed match rate − mean p|).
- **Label-free KPIs** (production has no truth): number of entities, largest cluster, cluster size distribution, review-queue size, match rate per source, score distribution, id drift.
- **Drift statistic:** population stability index, `PSI = Σ (a − e) × ln(a / e)` over bins of a reference (`e`) and current (`a`) distribution. Below 0.1 stable, 0.1–0.2 watch, above 0.2 act.
- **Golden set:** a few thousand steward-labelled pairs, stratified by score band, refreshed every quarter. It is how you measure precision and recall in production.

### 3.10 Identity drift

Identity drift is the same person getting a different id over time, or ids silently moving between people. Causes: rebuilding clusters from scratch, a new model version, a new source, threshold changes. Remedies:

- **Never regenerate ids.** Carry them forward: match new clusters to old ids by record overlap.
- **Splits:** the largest part keeps the id, the others get new ids with a `split_from` event.
- **Merges:** the older id survives; the other is retired with an **alias** so old references still resolve.
- **Measure it:** drift rate per run, splits and merges per run, and alert when they jump.

### 3.11 MLOps and feature stores

- **Feature store:** features are computed once, versioned, documented, and read by both training and serving. This prevents training/serving skew (for example a TF-IDF vocabulary refitted at scoring time). Offline store for training, online store for low-latency lookup when matching in real time.
- **Model registry:** every version with its metrics, feature-set version and artifact. Aliases (`champion`, `challenger`) instead of hard-coded versions.
- **Promotion gate:** automatic checks before an alias moves: quality at least as good, calibration acceptable, no new chaining. Shadow-score the challenger on live batches before switching.
- **Monitoring:** data quality on inputs (nulls, formats), score distribution PSI, label-free KPIs, id drift, and steward overturn rate (how often stewards reverse auto-matches).
- **Retraining loop:** steward labels → golden set → retrain → gate → promote, all logged in MLflow.

## 4. Code tour

### End-to-end flow

```text
data/generate_data.py
  |  customers.csv + new_batch.csv; true_entity_id / true_household_id are evaluation truth
  v
common/standardise.py
  |  cleaned names, contact fields, phonetic codes, unique_id
  +----------------------+----------------------+
  v                      v                      v
01_rules_rapidfuzz.py    02_splink.py         03_ml_recordlinkage.py
 rules + fuzzy score     EM probabilities     supervised pair model
  |                      |                      |
  +---------- pairs + clusters + metrics -------+
             |
             v
       04_graph_resolution.py   cannot-link repair, shared identifiers
             |
             v
       05_mdm.py                customer master + incremental batch
             |
             v
       06_customer_spine.py     hierarchy, households, spine, contracts
             |
       07_identity_drift.py     id stability across runs (uses the saved Splink model)
       08_mlops_feature_store.py feature store, registry, gate, monitoring
             |
             v
       09_compare.py            results/comparison.md
```

All three matchers use blocking to avoid testing every possible pair. Their scores are not interchangeable: the rules script produces a hand-weighted similarity score; Splink produces a probability from learned Fellegi-Sunter parameters; the ML script produces a classifier probability trained on synthetic truth. The thresholds in each script are therefore separate operating choices, not a shared calibration.

### 0. Generate the experiment: [data/generate_data.py](data/generate_data.py)

**Purpose:** make known-truth data so match quality can be measured reproducibly. `SEED`, `N_ENTITIES`, `N_NEW_BATCH` and `HOUSEHOLD_RATE` set the experiment. `make_entity()` creates the clean person-level truth; `add_households()` pairs about 10% of people into households that share an address, often a surname and sometimes a family email (it uses its own random generator); `noisy_copy()` generates source-specific records with realistic variations; `main()` creates the multi-source population and a later arrival batch.

**What gets written:** `data/customers.csv` is the initial population and `data/new_batch.csv` is the incremental feed. `true_entity_id` and `true_household_id` are the answer keys used by evaluation; they must not be treated as matching features in a real system. Later scripts carry them through for evaluation or label creation, but never use them as a blocking key or comparison feature.

**Why it matters:** without a known answer key, a demo can show plausible matches but cannot calculate false merges and missed links. The deterministic seed makes runs comparable, although Faker or library version changes can affect exact outputs.

### Shared foundation: [common/standardise.py](common/standardise.py)

**Purpose:** apply identical cleaning before candidate generation and comparison. `standardise()` copies the input, maps `source_record_id` to Splink's `unique_id`, then adds normalised names, nickname canonicalisation, email, phone, postcode, address, DOB, and metaphone fields. The smaller `clean_*` functions implement each field rule.

**Connection to the matchers:** every step calls `standardise(raw)`, including the MDM when it loads source rows and when it prepares records for incremental scoring. This single shared function is the first piece of the reusable framework.

**Design point:** normalisation makes formatting differences less informative, while fuzzy comparison handles remaining misspellings and variations. Production standardisation needs explicit locale, validation, and source-specific policies; these helpers are intentionally small teaching examples.

### Shared evaluation: [common/evaluate.py](common/evaluate.py)

**Purpose:** score predicted clusters against truth, not just inspect sample pairs. `evaluate_clusters()` calculates pairwise precision/recall/F1, B-cubed metrics, entity counts, largest cluster, false-merge pairs, and missed pairs. `blocking_recall()` measures pair completeness and reduction ratio. `union_find_clusters()` turns accepted pair edges into connected components.

**Interpretation:** pair metrics judge co-clustered pairs; B-cubed averages quality per record and stops large clusters dominating. `largest_cluster` is a useful chaining warning, not a quality metric by itself. The same function also evaluates households in step 6.

### 1. Hand-built matcher: [01_rules_rapidfuzz.py](01_rules_rapidfuzz.py)

**Input:** `data/customers.csv`. **Output:** `results/clusters_rapidfuzz.csv`, `results/review_queue_rapidfuzz.csv`, and `results/metrics_rapidfuzz.csv`.

1. `BLOCKING_KEYS` lists alternative field combinations. `candidate_pairs()` groups records by each key and unions the resulting pairs. Blocks over 200 records are skipped to avoid explosive comparisons from shared values such as generic contact details.
2. `score()` builds field-level similarities. `sim()` uses RapidFuzz for strings; exact values such as DOB and phone use exact agreement. Missing values are omitted and the remaining weights are renormalised.
3. `AUTO_MATCH` and `REVIEW` split scores into automatic edges, a review list, and rejected candidates.
4. `union_find_clusters()` converts auto-match edges into connected components; `evaluate_clusters()` compares these groups with truth.

**What to explain:** this is transparent because the team chose the fields, weights, blocking rules, and thresholds. It is also brittle: changes in source quality can require hand-retuning, and one erroneous edge can join otherwise separate components.

### 2. Probabilistic matcher: [02_splink.py](02_splink.py)

**Input:** `data/customers.csv`. **Outputs:** `results/splink_model.json`, `pairs_splink.csv`, `clusters_splink.csv`, `review_queue_splink.csv`, `splink_threshold_sweep.csv`, three HTML charts, and `metrics_splink.csv`.

1. `settings` declares the dedupe task, unique record ID, candidate-generation blocks, and field comparisons. Term-frequency adjustments reduce the weight of common names compared with rare names.
2. `build_linker()` registers the standardised data with DuckDB and creates the Splink `Linker`.
3. `train()` estimates the prior, estimates `u` using random pairs, and uses EM on three blocks to estimate `m` (section 3.5). No labels are supplied to training.
4. `predict()` scores candidate pairs; the low prediction threshold keeps candidates for later threshold decisions. Splink clusters at `CLUSTER_THRESHOLD`, 0.95.
5. The threshold sweep shows the precision/recall trade-off as a business decision. The saved JSON is the trained model reused by steps 5 and 7.

**What to explain:** on this data Splink's precision is 0.966, lower than the ML model, and 110 of its 198 false-merge pairs are household members. EM has learned, correctly, that address + surname + email agreement is very strong evidence, and two people who share a home and a mailbox produce exactly that. This sets up step 4.

### 3. Supervised matcher: [03_ml_recordlinkage.py](03_ml_recordlinkage.py)

**Input:** `data/customers.csv`. **Outputs:** `results/pairs_ml_features.csv` and `results/metrics_ml.csv`.

1. The script imports the blocking function from `01_rules_rapidfuzz.py`, so the model scores the same candidate pairs.
2. `features()` calculates name similarities, phonetic equality, exact date/contact/postcode agreement, and a character n-gram TF-IDF cosine over joined record text. It accepts an already fitted vectorizer, which step 8 uses for serving.
3. `main()` creates labels from the synthetic truth and trains two-fold cross-fitted gradient boosting, split by the left record's entity. This is out-of-fold but not strictly entity-disjoint; step 8 shows the strict version.
4. The script thresholds pair probabilities, forms connected components, evaluates clusters, and writes features with labels and out-of-fold probabilities.

**What to explain:** the feature/model approach can learn combinations that are awkward to hand-code, but these results use known synthetic truth. Pairwise AP is about 1.0 and clusters still contain false merges, so cluster metrics are the honest ones.

### 4. Graph resolution: [04_graph_resolution.py](04_graph_resolution.py)

**Inputs:** `data/customers.csv`, `results/pairs_splink.csv`, `results/pairs_ml_features.csv`. **Outputs:** `results/metrics_graph.csv`, `results/clusters_graph.csv` (repaired Splink clusters, used by the MDM), `results/shared_identifiers.csv`.

1. `build_graph()` makes a networkx graph: records are nodes, accepted pairs are edges weighted by probability.
2. `cannot_link()` combines two rules. `dob_conflict()`: both DOBs known and different, allowing a day/month swap. `name_conflict()`: canonical first names clearly different (Jaro-Winkler < 0.75, different metaphone), with no matching DOB and no sign of swapped first/last names.
3. `repair()` checks every component. When it finds a conflicting pair it runs `nx.minimum_cut` between them with probabilities as capacities, removes the cut edges, and re-checks both sides until no conflict remains.
4. `shared_identifiers()` builds the identifier view: every email or phone that points at more than one resolved person.

**What to explain:** for Splink, 46 components are split by cutting 85 edges; false-merge pairs drop from 198 to 12 and recall falls only from 0.965 to 0.961. For ML, false merges drop from 142 to 9 and B-cubed F1 rises to 0.992, the best in the demo. The constraints are business rules, so they are easy to explain and to audit. The shared-identifier list is a steward work queue and a candidate list of values to exclude from blocking.

### 5. Master-data workflow: [05_mdm.py](05_mdm.py)

**Inputs:** raw initial data, `results/clusters_graph.csv` (falls back to `clusters_splink.csv`), `results/splink_model.json`, and `data/new_batch.csv`. **Outputs:** `results/mdm.duckdb` plus golden-record, crosswalk, and review-queue CSV exports.

1. `MiniMDM.__init__()` creates the source, crosswalk (`xref`), current golden record, history, review, and audit tables in DuckDB.
2. `initial_load()` writes the source rows, maps each cluster to a generated `customer_id`, populates `xref`, and calls `rebuild_golden()`.
3. `survive()` chooses one winning non-empty value per field. Names and DOB use frequency, then source priority, then recency; contact fields use recency, then source priority. The JSON `provenance` records the source record and rule that won each field.
4. `rebuild_golden()` recomputes only touched customers, closes the previous open history version, increments the version, and inserts the new snapshot.
5. `score_new_records()` builds a Splink linker from the saved model and scores existing records against the new batch without retraining. `incremental_load()` attaches at p ≥ 0.95; otherwise it creates a new customer, and scores ≥ 0.50 enter review.
6. `approve_review()`, `reject_review()` and `unmerge_record()` are the steward actions; `unmerge_record()` validates a reason, writes `steward_audit` and rebuilds both golden records inside a transaction.
7. `erase_customer()` removes the customer's source rows, crosswalk, master, and history.

**Important distinction:** the normal script does not run `unmerge_record()`; see section 6. Customer IDs are stable within this database's lifecycle, but `main()` recreates the DuckDB file at startup.

### 6. Customer spine and hierarchy: [06_customer_spine.py](06_customer_spine.py)

**Inputs:** `results/mdm.duckdb` after step 5. **Outputs:** new tables `household`, `identity_hierarchy`, `customer_spine`, `column_classification` in the same database, plus `customer_spine.csv`, `identity_hierarchy.csv`, `spine_contracts.csv`, `metrics_households.csv`.

1. `households()` builds a graph of customers and address nodes. Every source record contributes its address (postcode + street line, fuzzy-matched at token-set ratio ≥ 85 within the postcode), so a customer whose golden address is a newer one still links to the home they share. Connected components are households, and each gets a rule: `single_person`, `same_address_same_surname` or `same_address`.
2. `build_hierarchy()` writes one parent-child table for all levels: HOUSEHOLD (root) → CUSTOMER → SOURCE, each edge with its rule and confidence.
3. `main()` creates `customer_spine`: one row per customer with household, golden attributes, source keys (`CRM:CRM-000123`), weakest link probability, golden version, match model version (a hash of the Splink JSON) and publish time.
4. `contracts()` runs seven data contracts: one customer per source record, no orphan source record, a golden record for every live customer, exactly one household per customer, every household exists, unique spine key, every PII column classified. Any violation stops the publish with a non-zero exit.

**What to explain:** this is the Golden Layer table downstream teams consume. Households are found for 75% of true same-household pairs at 97% precision; misses are people whose shared address never appears in their records (moves, web forms without an address). Governance is code: contracts run on every build, not in a document.

### 7. Identity drift: [07_identity_drift.py](07_identity_drift.py)

**Inputs:** `data/customers.csv`, `data/new_batch.csv`, `results/splink_model.json`. **Outputs:** `results/identity_drift.csv`, `id_alias.csv`, `id_events.csv`.

1. `cluster()` scores and clusters a snapshot with the saved model, without retraining.
2. Run 1 clusters the initial data. Run 2 clusters a later snapshot: 5% of records get a new phone or lose their email, and the new batch is added. Everything is re-clustered from scratch.
3. Three id strategies are compared: `sequential()` (renumber every run), representative (a member record id), and `carry_forward()`, which gives each run-2 cluster the run-1 id it overlaps most, keeps the id for the largest part of a split, retires the younger id on a merge and records an alias.
4. `drift()` reports the share of run-1 records whose id changed; `membership_changed()` gives context: how many records really moved cluster.

**What to explain:** sequential numbering changes 56% of ids, the representative id 0.87%, carry-forward 0.20%, while 0.51% of records sit in a cluster that really changed. Carry-forward produced 201 new ids, 11 splits and 5 merges with aliases. Ids are a product with consumers, so their stability is a metric.

### 8. MLOps and feature store: [08_mlops_feature_store.py](08_mlops_feature_store.py)

**Inputs:** `data/customers.csv`, `data/new_batch.csv`. **Outputs:** `results/feature_store.duckdb`, `results/model_registry/` (pickled models and `registry.json`), `model_versions.csv`, `monitoring_report.csv`, and `results/mlruns` if MLflow is installed.

1. `FeatureStore` holds `feature_definitions` and versioned pair-feature tables. The feature-set version is a hash of the feature names and the fitted TF-IDF vocabulary. `read()` refuses features whose version differs from the model's.
2. The training pairs are written to the store and read back, as a scheduled training job would.
3. A strict **entity-disjoint split** puts a third of people in the test set; only pairs with both records in train (or both in test) are used.
4. Two versions are trained: logistic regression and gradient boosting. `evaluate()` reports average precision, Brier, ECE and B-cubed on test clusters. `register()` saves each version; `promotion_gate()` moves the `champion` alias only if B-cubed F1 is at least the champion's, ECE ≤ 0.05 and chaining is no worse.
5. Monitoring scores the real new batch and a **broken feed** (phones missing, first names reduced to initials) with the champion, reading features through the store with the training vectorizer. `monitor()` reports candidate pairs, match rate, grey-zone share, and PSI of the score and of every feature.

**What to explain:** v2 (B-cubed 0.993, ECE 0.004) beats v1 (0.987, 0.012) and is promoted. The normal batch has score PSI 0.03 and no alerts. The broken feed has score PSI 2.77 and four alerts, yet its match rate looks better (0.98 against 0.89) because a third of its candidate pairs disappeared. One KPI alone would have hidden the incident.

### 9. Report: [09_compare.py](09_compare.py)

Collects every metric CSV into `results/comparison.md`: the matcher table, households, spine contracts, drift, model versions and monitoring. It does not recompute anything; missing inputs are skipped.

### Optional integrations: [databricks/splink_on_databricks.py](databricks/splink_on_databricks.py) and [zingg/zingg_customers.py](zingg/zingg_customers.py)

`databricks/splink_on_databricks.py` translates the local Splink path to SparkAPI, Delta tables in Unity Catalog, and MLflow logging. It expects a Databricks-provided `spark` session, a Silver table, a checkpoint volume and a compatible Splink install. It is a design example, not part of the verified laptop pipeline.

`zingg/zingg_customers.py` describes a separate active-learning workflow on Spark. Its phase argument selects `findTrainingData`, `label`, `train`, or `match`; `FieldDefinition` controls which fields are ignored, exact, or fuzzy. Check the Python API against the installed Zingg version before running it.

## 5. Ten-minute walkthrough

| Time | Show | Say |
|---|---|---|
| 1 min | `data/customers.csv`, `results/comparison.md` | Three systems, 8,192 records, 4,000 people, 183 households. The generator keeps the truth, so every error is countable. |
| 1 min | `01_rules_rapidfuzz.py` output | Blocking, weighted fuzzy score, thresholds, Union-Find. Explainable, F1 0.93, and hand-tuned. |
| 2 min | Splink metrics, `splink_waterfall_example.html` | Weights learned with EM and no labels; the waterfall is the explanation for a steward. Precision 0.966: households sharing an address and a mailbox look like one person. |
| 1 min | `03_ml_recordlinkage.py` output | Labels give the best recall. AP ≈ 1.0 and clusters still chain, so evaluate clusters. |
| 2 min | `04_graph_resolution.py` output, `shared_identifiers.csv` | A customer is a component. Cannot-link rules plus a min cut take false merges from 198 to 12. The shared-identifier list goes to stewards and to the blocking exclusion list. |
| 1 min | `customer_spine` and `identity_hierarchy` in DuckDB | Golden record with provenance, crosswalk, history, household → customer → source, published only when seven contracts pass. |
| 1 min | `identity_drift.csv`, `monitoring_report.csv` | Naive rebuild changes 56% of ids, carry-forward 0.2%. Registry with a promotion gate; a broken feed fires four PSI alerts while the match rate looks better. |
| 1 min | README section 7 | How it maps to Bronze/Silver/Gold, SparkAPI, GraphFrames, Unity Catalog feature tables, MLflow and Workflows. Be clear that Databricks and Zingg were not executed here. |

Use `results/comparison.md` as the source for exact metrics. The documented values depend on the fixed seed and package versions; do not imply they are expected production metrics.

## 6. Optional: demonstrate un-merge

The normal `05_mdm.py` run does not call `unmerge_record`; it does run an approval and erasure example. To demonstrate un-merge, run this snippet from PowerShell after the demo run. It changes `results/mdm.duckdb` and does not refresh the CSV exports or the spine. Re-run the pipeline to restore the original demo state.

```powershell
@'
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("mdm_demo", "05_mdm.py")
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

Explain that the source row is assigned a new customer ID, the old and new golden records are rebuilt, history is versioned, and the steward reason is written to `steward_audit`. This is a single-record correction, not general cluster splitting.

## 7. System design: the framework at scale

A likely question in the client interview: "How would you build our identity-resolution framework?" Answer in this order, about five minutes, drawing boxes if there is a whiteboard.

1. **Clarify:** how many customers and sources, batch or real-time, B2C or B2B, which consumers depend on the id, what a false merge costs, who the stewards are.
2. **Ingest and standardise (Bronze → Silver):** one table per source, a standardisation library shared by every job, data-quality checks on arrival (nulls, formats, junk values).
3. **Candidate generation:** several blocking rules, block-size caps, a generic-identifier exclusion list fed by the identifier graph; measure pair completeness on the golden set.
4. **Scoring in tiers:** deterministic rules for certain links (same verified email + DOB), a probabilistic model (Splink on Spark) for the bulk, a supervised or active-learning model only where the grey zone is large. Thresholds per business use: marketing can accept more risk than finance.
5. **Graph layer:** connected components, cannot-link constraints and repair, household and company hierarchies, shared-identifier detection. GraphFrames on Spark, or a graph database if the hierarchy is queried online.
6. **Mastering:** carry-forward ids, survivorship with provenance, SCD2 history, crosswalk, steward workflow with audit.
7. **Golden Layer:** the customer spine and hierarchy tables in Gold, published only when contracts pass, PII tagged and masked, lineage in the catalogue.
8. **Real-time path (if needed):** an online feature store with standardised attributes and blocking keys; a new record looks up candidates by key, is scored by the same model and gets an id in milliseconds; the nightly batch reconciles.
9. **MLOps:** feature store, registry with champion/challenger, promotion gate, shadow scoring, monitoring of PSI, label-free KPIs, id drift and steward overturn rate; retraining from steward labels.
10. **Reusability:** the matcher is configuration (blocking rules, comparisons, thresholds, survivorship rules per field) so a new source or a new entity type (supplier, product) is a config change, not a new project.

## 8. Questions to expect

### Fundamentals

- **Why not match every pair?** There are 33.5 million possible pairs here; blocking keeps 96.5% of true pairs while evaluating 6,405. At 30 million records all-pairs is impossible.
- **Deterministic or probabilistic?** Both, in tiers. Deterministic for certain links and for explainability; probabilistic or ML where data is noisy and rules miss or over-match.
- **Explain Fellegi-Sunter in one minute.** Section 3.5: `m` and `u` per field level, weight `log2(m/u)`, weights add up, prior from λ, EM gives `m` without labels.
- **What does term-frequency adjustment do?** Agreement on a rare surname counts more than on `Smith`, using the value's frequency.
- **Jaro-Winkler or Levenshtein?** Jaro-Winkler for short strings like names (rewards common prefixes); Levenshtein or edit distance for codes and longer strings; token-based ratios when word order varies.

### Graphs

- **Where do graphs help in identity resolution?** Clustering (components), chaining detection and repair, shared identifiers, households and company hierarchies, propagating identity across sources that never share a field directly.
- **Matching is not transitive. What do you do?** Evaluate clusters, cap or inspect large components, add cannot-link constraints, cut the weakest edges (min cut), or use correlation clustering or community detection.
- **How would you scale the graph step?** GraphFrames connected components on Spark; repair only components that contain a conflict, which is a small fraction; a graph database only for online traversal.

### ML and confidence

- **Where do labels come from?** Steward decisions on the review queue, a stratified golden set, active learning to pick the most informative pairs.
- **How do you avoid leakage?** Split by entity, never by pair; `08` shows the strict split.
- **What does "confidence" mean for a match?** A calibrated probability. Check calibration (Brier, ECE) before using thresholds; recalibrate with isotonic or Platt scaling.
- **Why favour precision?** A false merge can expose one person's data to another and corrupt consent and credit decisions. Keep uncertain records in the review queue instead of joining them.

### Spine, MDM and governance

- **What is a customer spine?** The governed table of resolved customer ids with hierarchy and source keys that every domain joins to; section 3.8.
- **How do you build a governed hierarchy?** Explicit levels, one parent per child, a rule and confidence on every edge, contracts that check the shape on every build, history of changes.
- **Survivorship rules?** Per field: trust, recency, frequency, completeness; always with provenance.
- **How do you handle GDPR erasure?** Delete from source copies, crosswalk, golden record, history and features; vacuum old file versions; keep only a non-identifying erasure log.

### Drift, MLOps and feature stores

- **What is identity drift and how do you reduce it?** Section 3.10; quote 56% → 0.2%.
- **How do you deploy a new matching model safely?** Register, evaluate on the golden set, gate, shadow-score on live batches, compare label-free KPIs and id drift, then move the alias; roll back by moving it back.
- **What do you monitor without labels?** Number of entities, largest cluster, review queue size, match rate per source, score PSI, id drift, steward overturn rate.
- **Why a feature store here?** Same standardised attributes and pair features for training, batch and real-time scoring; versioned so a model never reads features it was not trained on; reusable across matching use cases.

### What is not production-ready

The MDM, spine and registry are teaching models: no concurrent write handling, steward UI, access control or real-time path. Synthetic data is cleaner than real customer data. The cannot-link rules trust the DOB. Zingg and Databricks were not executed.

## 9. Your own stories

The interviewers will ask for experience, not only the demo. Prepare one short story (situation, what you did, measurable result) for each prompt; the README mentions CloserStill, Mars and Genus as starting points.

- A matching system you built: data size, sources, approach, quality before and after.
- A false merge or generic-identifier problem you found and how you fixed it.
- Deploying and monitoring a model in production: what broke and how you noticed.
- Working with data stewards or business owners to agree thresholds and survivorship rules.
- Making a framework reusable across teams or entity types.

## 10. Glossary

| Term | Meaning |
|---|---|
| Blocking | Restricting comparisons to records that share a cheap key |
| Pair completeness | Share of true pairs that survive blocking |
| m / u probability | P(agreement level given match) / given non-match |
| Match weight | log2(m/u), summed over fields plus the prior |
| EM | Expectation-maximisation: estimates `m` without labels |
| B-cubed | Per-record cluster precision and recall |
| Chaining | One bad edge merging two clusters through transitive closure |
| Cannot-link | A rule that two records are different entities |
| Minimum cut | Cheapest set of edges whose removal separates two nodes |
| Golden record | The best surviving values for one entity |
| Survivorship | Rules that choose each golden value |
| Provenance | Which source record and rule produced each value |
| Crosswalk (xref) | Map from source ids to the master id |
| Customer spine | Governed table of resolved customer ids that domains join to |
| Golden Layer | The Gold layer of the lakehouse that publishes mastered data |
| Identity drift | A person's id changing between runs, or ids moving between people |
| Carry-forward | Assigning new clusters the old id they overlap most |
| Feature store | Versioned, shared features for training and serving |
| PSI | Population stability index, a distribution-shift statistic |
| ECE | Expected calibration error |
| Champion / challenger | Current production model / candidate replacement |

## 11. Troubleshooting

- If an output is missing, rerun the steps in order; later stages consume earlier CSVs, the saved Splink model and `mdm.duckdb`.
- If `06_customer_spine.py` exits with "data contract failed", re-run `05_mdm.py` first: the spine expects a freshly built MDM database.
- If PowerShell cannot find `python`, install Python 3.13 or use the Python launcher to create the virtual environment, then continue with `.venv`'s interpreter.
- If a Splink chart does not open, use the browser's Open File action and select it from `results/`.
- If a DuckDB file is locked, close any SQL client that has it open and run again.
- The Databricks and Zingg examples require their own runtimes and are not validated by the local run.
