# Code guide: every script, line by line

Versión en español: [CODE_GUIDE.es.md](CODE_GUIDE.es.md)

This guide explains each Python script in the demo in detail. Every block of code links to the exact lines it describes, names the slide of the deck ([slides/customer-identity-resolution.pptx](slides/customer-identity-resolution.pptx)) where the idea is shown, and points to the matching section of the [DEMO_GUIDE](DEMO_GUIDE.md) for the theory. The code itself is commented in English, statement by statement, so you can read the script and this guide side by side.

How to use it:
- Read the [DEMO_GUIDE](DEMO_GUIDE.md) concepts first if a term is new, then come here to see how the code does it.
- Open the script next to this page. Links such as [01_rules_rapidfuzz.py#L73-L92](01_rules_rapidfuzz.py#L73-L92) jump to those lines on GitHub.
- The "What you should see" blocks are the exact lines the script prints with the fixed seed (42) and the pinned requirements, so your run should match them number for number.
- Line numbers refer to the current version of each file. If you edit a script, the links after your edit will drift.

## Contents

1. [Run order](#run-order)
2. [Slide to code map](#slide-to-code-map)
3. Shared code: [data/generate_data.py](#datagenerate_datapy), [common/standardise.py](#commonstandardisepy), [common/evaluate.py](#commonevaluatepy)
4. Matching: [01_rules_rapidfuzz.py](#01_rules_rapidfuzzpy), [02_splink.py](#02_splinkpy), [03_ml_recordlinkage.py](#03_ml_recordlinkagepy)
5. Graphs: [04_graph_resolution.py](#04_graph_resolutionpy)
6. Mastering: [05_mdm.py](#05_mdmpy), [06_customer_spine.py](#06_customer_spinepy), [07_identity_drift.py](#07_identity_driftpy)
7. MLOps: [08_mlops_feature_store.py](#08_mlops_feature_storepy)
8. Report and runner: [09_compare.py](#09_comparepy), [run_all.sh](#run_allsh)
9. Not run locally: [databricks/splink_on_databricks.py](#databrickssplink_on_databrickspy), [zingg/zingg_customers.py](#zinggzingg_customerspy)

## Run order

```text
data/generate_data.py      -> data/customers.csv, data/new_batch.csv
01_rules_rapidfuzz.py      -> results/clusters_rapidfuzz.csv, review_queue_rapidfuzz.csv, metrics_rapidfuzz.csv
02_splink.py               -> results/clusters_splink.csv, pairs_splink.csv, splink_model.json, review_queue_splink.csv, splink_threshold_sweep.csv, metrics_splink.csv
03_ml_recordlinkage.py     -> results/pairs_ml_features.csv, metrics_ml.csv
04_graph_resolution.py     -> results/clusters_graph.csv, shared_identifiers.csv, metrics_graph.csv
05_mdm.py                  -> results/mdm.duckdb, mdm_golden_record.csv, mdm_xref.csv, mdm_review_queue.csv
06_customer_spine.py       -> results/customer_spine.csv, identity_hierarchy.csv, spine_contracts.csv, metrics_households.csv
07_identity_drift.py       -> results/id_alias.csv, id_events.csv, identity_drift.csv
08_mlops_feature_store.py  -> results/feature_store.duckdb, model_registry/, model_versions.csv, monitoring_report.csv
09_compare.py              -> results/comparison.md (the table behind slide 27)
```

Every script reads the shared cleaning in [common/standardise.py](common/standardise.py) and the shared metrics in [common/evaluate.py](common/evaluate.py), so all matchers are scored the same way.

## Slide to code map

| Slide | Topic | Where in the code |
|---|---|---|
| 2, 5 | One person, three systems; synthetic data | [data/generate_data.py](#datagenerate_datapy) |
| 4 | Pipeline | [Run order](#run-order), [run_all.sh](#run_allsh) |
| 7 | Blocking | [01_rules_rapidfuzz.py](#01_rules_rapidfuzzpy) `candidate_pairs()`, [02_splink.py](#02_splinkpy) blocking rules |
| 8 | Three ways to score a pair | [01](#01_rules_rapidfuzzpy) `score()`, [02](#02_splinkpy), [03](#03_ml_recordlinkagepy) |
| 9, 10 | Fellegi-Sunter, m/u, adding up bits | [02_splink.py](#02_splinkpy) |
| 11, 12 | Supervised features and labels | [03_ml_recordlinkage.py](#03_ml_recordlinkagepy) |
| 13 | Precision or recall | thresholds in [01](#01_rules_rapidfuzzpy), [02](#02_splinkpy), [03](#03_ml_recordlinkagepy); metrics in [common/evaluate.py](#commonevaluatepy) |
| 15, 16, 17 | Why pair scores lie, cannot-link, min cut | [04_graph_resolution.py](#04_graph_resolutionpy) |
| 19 | Mini MDM | [05_mdm.py](#05_mdmpy) |
| 20 | Customer spine and hierarchy | [06_customer_spine.py](#06_customer_spinepy) |
| 21 | Identity drift | [07_identity_drift.py](#07_identity_driftpy) |
| 23, 24 | Feature store, registry, gate, monitoring | [08_mlops_feature_store.py](#08_mlops_feature_storepy) |
| 25, 26 | Lakehouse and framework at scale | [databricks/splink_on_databricks.py](#databrickssplink_on_databrickspy), [zingg/zingg_customers.py](#zinggzingg_customerspy) |
| 27 | Results chart | [09_compare.py](#09_comparepy) |

---

## data/generate_data.py

**What it does:** builds the experiment. It invents 4,400 clean "true" people with Faker, pairs some of them into households, then writes several deliberately messy copies of the first 4,000 people across three source systems (CRM, WEB, BILLING). It also writes a later batch of 400 records, half returning people and half brand-new people. Because the people exist before their copies, every record carries the id of the person it really belongs to, which is what lets every later step count false merges and missed links.

**Run:** `python data/generate_data.py` (first line of [run_all.sh](run_all.sh)). Takes a couple of seconds.

**Reads / Writes:** reads nothing. Writes `data/customers.csv` (initial population) and `data/new_batch.csv` (incremental feed read by `05_mdm.py`, `06_customer_spine.py`, `07_identity_drift.py` and `08_mlops_feature_store.py`). The columns `true_entity_id` and `true_household_id` are answer keys for evaluation only; no matcher uses them as a feature or blocking key.

**Slides:** 2 (One person, three systems), 5 (Synthetic data), 20 (households feed the customer spine).

**Guide:** [3.1 The problem](DEMO_GUIDE.md#31-the-problem), [0. Generate the experiment](DEMO_GUIDE.md#0-generate-the-experiment-datagenerate_datapy), [1. Run the demo](DEMO_GUIDE.md#1-run-the-demo).

**Walkthrough**

1. [data/generate_data.py#L1-L22](data/generate_data.py#L1-L22) Module docstring: what noise is injected, why synthetic data is needed (you can only measure ER when you know the answer), the outputs and the related slides.
2. [data/generate_data.py#L24-L37](data/generate_data.py#L24-L37) Imports. `random` drives every noise coin flip, `Faker` makes UK-looking names and addresses, and the Faker `date_time` provider is imported twice because it gets patched below.
3. [data/generate_data.py#L39-L49](data/generate_data.py#L39-L49) Experiment settings and seeding. `SEED`, `N_ENTITIES`, `N_NEW_BATCH` and `HOUSEHOLD_RATE` control everything downstream; seeding both `random` and Faker makes every run produce identical data, which is why the demo numbers are reproducible (slide 5).
4. [data/generate_data.py#L52-L63](data/generate_data.py#L52-L63) `_rand_seconds` patch. Faker picks random timestamps with `randint` on Windows and `uniform` elsewhere, so the same seed produced different people per OS. Forcing `uniform` gives one dataset everywhere.
5. [data/generate_data.py#L66-L76](data/generate_data.py#L66-L76) `_FixedNow` freezes "today" at 2026-10-19 so ages and "last 3 years" timestamps do not move with the calendar. Without it, rerunning next month would change dates of birth and `updated_at` values.
6. [data/generate_data.py#L78-L105](data/generate_data.py#L78-L105) `NICKNAMES` (formal name to nickname, used to inject noise; [common/standardise.py](common/standardise.py) holds the reverse map), the three `SOURCES` from slide 2, and the output folder `OUT`.
7. [data/generate_data.py#L108-L127](data/generate_data.py#L108-L127) `typo()`: one keyboard error per call (transposition, deletion, insertion or substitution) at an inner position. These are exactly the edits that edit-distance and Jaro-Winkler comparisons are designed to forgive (slide 8).
8. [data/generate_data.py#L130-L146](data/generate_data.py#L130-L146) `phone_format()`: the same number rendered as raw, spaced, `+44` international or dashed. Pure formatting noise, which `clean_phone()` removes; it shows why standardisation comes before matching (slide 4).
9. [data/generate_data.py#L149-L178](data/generate_data.py#L149-L178) `make_entity()`: one clean ground-truth person. 25% of first names are forced to nickname-able names so the nickname problem actually appears; email is `first.last[nn]@provider`.
10. [data/generate_data.py#L181-L252](data/generate_data.py#L181-L252) `noisy_copy()`: the heart of the generator. It copies a person into one source record and applies independent noise: nicknames, typos, swapped first/last name, upper case ([L194-L209](data/generate_data.py#L194-L209)); DOB day/month swap or missing ([L211-L216](data/generate_data.py#L211-L216)); email missing, typo or upper case, at most one ([L218-L227](data/generate_data.py#L218-L227)); phone missing or reformatted ([L229-L230](data/generate_data.py#L229-L230)); moved house or abbreviated address and postcode formatting ([L232-L246](data/generate_data.py#L232-L246)); and source-specific gaps, WEB without address and BILLING without DOB ([L247-L251](data/generate_data.py#L247-L251)). The "moved house" branch is important: it creates true matches with no address evidence, which is why no single field can decide a match (slide 9).
11. [data/generate_data.py#L255-L283](data/generate_data.py#L255-L283) `add_households()`: pairs 220 people (10% of 4,400) into two-person households that share an address; 60% also share a surname, 25% share a family mailbox such as `thesmiths@gmail.com`. It uses its own `random.Random(SEED + 1)` so adding households does not shift the person-level noise. These households create the "different people, same address and surname" false-merge risk (slides 15 to 17) and the shared-identifier problem in `04_graph_resolution.py`.
12. [data/generate_data.py#L286-L301](data/generate_data.py#L286-L301) `main()`, initial population: create all 4,400 people, add households, then give each of the first 4,000 people 1 to 3 source systems (35/40/25%) and a 7% chance of a duplicate inside the same system.
13. [data/generate_data.py#L303-L315](data/generate_data.py#L303-L315) New batch: even positions are a random existing person (should attach to an existing customer), odd positions are one of the reserved extra people (should become a new customer). This 50/50 split is what makes `05_mdm.py`'s "197/200 returning attached correctly" measurable.
14. [data/generate_data.py#L317-L341](data/generate_data.py#L317-L341) Fix the column order, shuffle rows with `sample(frac=1)` so duplicates are not adjacent, and write both CSVs.
15. [data/generate_data.py#L342-L349](data/generate_data.py#L342-L349) Print the three summary lines, including how many households in the initial data really hold two people.

**What you should see**

```text
customers.csv: 8192 records for 4000 people
new_batch.csv: 400 records
households with 2 people: 183
```

8,192 records for 4,000 people means about 2.05 records per person, so most people have at least one duplicate to find. 183 is below the 220 household pairs created because pairs were drawn from all 4,400 people and some housemates belong to the 400 reserved for the new batch.

**Try this**

1. Set `HOUSEHOLD_RATE = 0.30` and rerun the whole pipeline: more people share address and surname, so false merges in `01_rules_rapidfuzz.py` and `02_splink.py` rise and the graph repair in `04_graph_resolution.py` has more to cut.
2. Raise the moved-house probability on [L232](data/generate_data.py#L232) from 0.15 to 0.40: address agreement becomes weaker evidence, recall drops, and Splink learns a lower `m` for address.
3. Change `SEED` to 7: every count moves slightly, which shows how much of a difference between matchers is noise versus a real effect.

---

## common/standardise.py

**What it does:** the shared cleaning step that every matcher runs before blocking and scoring. Small `clean_*` functions remove pure formatting differences (case, accents, titles, phone formats, postcode spacing, Gmail dots and plus-tags), and `standardise()` applies them to a whole DataFrame and adds derived keys: a canonical first name for nicknames, phonetic codes, the email user part and the postcode area. Running one function everywhere means the rules, Splink and ML matchers all see identical inputs, so their results are comparable.

**Run:** not run directly. Imported as `from common.standardise import standardise` by `01` to `05`, `07` and `08` (`05_mdm.py` also uses it for the incremental batch).

**Reads / Writes:** no files. Input is the raw DataFrame from `data/customers.csv` or `data/new_batch.csv`; output is a cleaned copy with extra columns `unique_id`, `first_name_canon`, `email_user`, `postcode_area`, `surname_metaphone`, `first_metaphone`.

**Slides:** 4 (Pipeline, standardise stage), 7 (Blocking: the derived keys are blocking keys), 8 (Three ways to score a pair: all three score these cleaned fields), 10 (Robert Smith vs Bob Smyth: nickname map and metaphone are what make that pair look alike).

**Guide:** [3.2 Standardisation](DEMO_GUIDE.md#32-standardisation), [3.3 Blocking (indexing)](DEMO_GUIDE.md#33-blocking-indexing), [Shared foundation](DEMO_GUIDE.md#shared-foundation-commonstandardisepy).

**Walkthrough**

1. [common/standardise.py#L1-L16](common/standardise.py#L1-L16) Module docstring: why standardise first (formatting differences should not cost match evidence), input, output columns and slides.
2. [common/standardise.py#L18-L25](common/standardise.py#L18-L25) Imports: `re` for regular expressions, `unicodedata` for accent removal, `jellyfish` for the Metaphone phonetic code.
3. [common/standardise.py#L27-L55](common/standardise.py#L27-L55) `NICKNAMES`: nickname to formal name. It is the reverse of the generator's map plus a few extra forms (`rob`, `will`, `beth`, `jimmy`, `katie`). This is the "Bob" to "robert" step on slide 10.
4. [common/standardise.py#L56-L58](common/standardise.py#L56-L58) `TITLES`: a compiled regex that removes honorifics (`mr`, `dr.`, ...) as whole words only.
5. [common/standardise.py#L61-L73](common/standardise.py#L61-L73) `clean_name()`: blank to `None`, accents stripped with NFKD, lowercase, titles removed, then only letters, spaces, apostrophes and hyphens kept. Returning `None` instead of `""` matters: Splink and the ML features treat `None` as "no evidence" rather than as a disagreement.
6. [common/standardise.py#L76-L88](common/standardise.py#L76-L88) `clean_email()`: lowercase, drop `+tag`, and remove dots only for Gmail, because only Gmail ignores them. Applying the dot rule to every provider would create false email matches.
7. [common/standardise.py#L91-L101](common/standardise.py#L91-L101) `clean_phone()`: keep digits, turn a leading `44` into `0`, reject anything shorter than 10 digits. After this, the four formats from `phone_format()` in the generator collapse to one value, so exact phone agreement becomes strong evidence.
8. [common/standardise.py#L104-L112](common/standardise.py#L104-L112) `clean_postcode()`: uppercase, remove spaces, re-insert the space before the last 3 characters (the UK inward code).
9. [common/standardise.py#L115-L153](common/standardise.py#L115-L153) `standardise()`: copies the input (the raw values stay available for golden records), sets `unique_id` (the column name Splink requires), cleans names and builds `first_name_canon` ([L121-L128](common/standardise.py#L121-L128)), cleans email and adds `email_user` ([L129-L131](common/standardise.py#L129-L131)), cleans phone and postcode and adds `postcode_area` ([L132-L136](common/standardise.py#L132-L136)), normalises address whitespace ([L137-L140](common/standardise.py#L137-L140)), parses DOB to `YYYY-MM-DD` with unparseable values as missing ([L141-L143](common/standardise.py#L141-L143)), and finally adds Metaphone codes for surname and canonical first name ([L144-L152](common/standardise.py#L144-L152)). `smith` and `smyth` both encode to `SM0`, so a blocking rule on `dob + surname_metaphone` still pairs them despite the spelling difference (slide 7).

**What you should see:** nothing is printed by this module. Its effect shows in the next step's blocking line, `blocking: {'candidate_pairs': 6405, 'pair_completeness': 0.9649, 'reduction_ratio': 0.999809}` from `01_rules_rapidfuzz.py`: 96.5% of true pairs survive blocking on these cleaned keys while 99.98% of the 33.5 million possible pairs are skipped. You can also inspect it directly:

```python
import pandas as pd
from common.standardise import standardise
standardise(pd.read_csv("data/customers.csv")).head()
```

**Try this**

1. Remove the Gmail branch ([L85-L87](common/standardise.py#L85-L87)) and rerun `01_rules_rapidfuzz.py`: expect little or no change, because the generator never adds Gmail dots, which is a reminder that a rule only helps if the noise exists in your data.
2. Empty the `NICKNAMES` dict: `first_name_canon` equals `first_name`, the `first_name_canon + last_name` blocking rule loses Bob/Robert pairs, and pair completeness and recall fall.
3. Change `clean_phone()` to return `d` without the length check: short broken numbers start agreeing exactly, which can create false merges.

---

## common/evaluate.py

**What it does:** the answer-key scorer shared by every step. `evaluate_clusters()` compares predicted clusters with `true_entity_id` and reports pairwise precision/recall/F1, B-cubed precision/recall/F1, entity counts, the largest cluster, false-merge pairs and missed pairs. `blocking_recall()` measures how many true pairs survive blocking. `union_find_clusters()` turns accepted pair links into clusters (connected components). Because every matcher is scored by the same code, the numbers in the final comparison are like for like.

**Run:** not run directly. Imported by `01_rules_rapidfuzz.py`, `02_splink.py`, `03_ml_recordlinkage.py`, `04_graph_resolution.py`, `06_customer_spine.py` (households) and `08_mlops_feature_store.py`.

**Reads / Writes:** no files. Inputs are record ids, predicted cluster labels and true labels; output is a plain `dict` that each step prints and saves as a `results/metrics_*.csv` row.

**Slides:** 12 (Labels: truth makes measurement possible), 13 (Precision or recall), 15 (Why pair scores lie: union-find chaining and `largest_cluster`), 27 (Results chart, built from these metrics).

**Guide:** [3.9 Matching-quality metrics](DEMO_GUIDE.md#39-matching-quality-metrics), [Precision or recall: which matters more?](DEMO_GUIDE.md#precision-or-recall-which-matters-more), [3.3 Blocking (indexing)](DEMO_GUIDE.md#33-blocking-indexing), [Step 3. Chaining](DEMO_GUIDE.md#step-3-chaining-why-one-bad-edge-is-enough), [Shared evaluation](DEMO_GUIDE.md#shared-evaluation-commonevaluatepy).

**Walkthrough**

1. [common/evaluate.py#L1-L16](common/evaluate.py#L1-L16) Module docstring: the two metric families, the helper functions, and how to read `false_merges_pairs`, `missed_pairs` and `largest_cluster`.
2. [common/evaluate.py#L18-L23](common/evaluate.py#L18-L23) Imports: `combinations` enumerates unordered pairs; `Counter` builds a size histogram.
3. [common/evaluate.py#L26-L36](common/evaluate.py#L26-L36) `_pairs()`: for each cluster, every sorted pair of its records. A cluster of size k gives k(k-1)/2 pairs, which is why pairwise metrics are dominated by big clusters: one wrong 9-record cluster costs many pairs.
4. [common/evaluate.py#L39-L52](common/evaluate.py#L39-L52) Pairwise metrics in `evaluate_clusters()`: build predicted and true pair sets, then precision = correct merged pairs / merged pairs and recall = correct merged pairs / true pairs (slide 13).
5. [common/evaluate.py#L54-L70](common/evaluate.py#L54-L70) B-cubed: for each record, compare its predicted cluster with its true cluster; precision is the share of my cluster that is really me, recall is the share of my real records that I am grouped with. Averaging per record gives every record equal weight, so B-cubed is less sensitive to a few large clusters.
6. [common/evaluate.py#L72-L91](common/evaluate.py#L72-L91) The result dict. `false_merges_pairs` and `missed_pairs` are set differences of the pair sets; `largest_cluster` is the chaining alarm. Line 73 builds a `sizes` histogram that is not returned.
7. [common/evaluate.py#L94-L107](common/evaluate.py#L94-L107) `blocking_recall()`: pair completeness (true pairs that blocking kept, a ceiling on recall because no model can match a pair it never sees) and reduction ratio (share of the n(n-1)/2 possible pairs that were skipped) (slide 7).
8. [common/evaluate.py#L110-L131](common/evaluate.py#L110-L131) `union_find_clusters()`: a disjoint-set structure with path halving. Each accepted pair joins two clusters; A-B and B-C put A and C together even if A-C scored low. That transitive closure is the chaining effect that `04_graph_resolution.py` repairs (slides 15 to 17). The smaller root always wins, so cluster ids are deterministic.

**What you should see:** this module prints nothing; its dicts appear in other steps' output. For example `01_rules_rapidfuzz.py` prints:

```text
blocking: {'candidate_pairs': 6405, 'pair_completeness': 0.9649, 'reduction_ratio': 0.999809}
quality: {'pair_precision': 0.9523, 'pair_recall': 0.9127, 'pair_f1': 0.9321, 'bcubed_precision': 0.9882, 'bcubed_recall': 0.9539, 'bcubed_f1': 0.9707, 'n_records': 8192, 'n_pred_entities': 4278, 'n_true_entities': 4000, 'largest_cluster': 9, 'false_merges_pairs': 267, 'missed_pairs': 510}
```

Read it as: 95.2% of merged pairs are correct, but 267 pairs of different people were merged and 510 true pairs were missed; 4,278 predicted customers against 4,000 real people means under-merging overall; B-cubed F1 (0.971) is higher than pair F1 (0.932) because per-record scoring weighs small, correct clusters more. Splink scores 198 false merges / 205 missed, the ML matcher 142 / 145, and after graph repair 12 (Splink) and 9 (ML).

**Try this**

1. In a Python shell, call `evaluate_clusters([1, 2, 3, 4], ["a", "a", "a", "a"], [1, 1, 2, 2])`: one merged cluster of two people gives pair precision 0.3333 (2 of 6 pairs correct), B-cubed precision 0.5, recall 1.0 and 4 false-merge pairs: the textbook false merge.
2. Call `union_find_clusters([1, 2, 3], [(1, 2), (2, 3)])`: all three land in cluster 1 even though (1, 3) was never matched. That is chaining in three lines.
3. Compare pair precision with B-cubed precision on the rapidfuzz row: the gap shows how much a few large wrong clusters weigh in pairwise scoring.

---

## 01_rules_rapidfuzz.py

**What it does.** The hand-built matcher. It cleans the records, proposes candidate pairs with five cheap blocking keys, scores each pair with hand-chosen weights over RapidFuzz similarities, and splits the scores into auto-match, review and no-match bands. Auto-matches become graph edges and connected components (Union-Find) become the predicted customers. It is the baseline the probabilistic and supervised matchers are compared against, and its `candidate_pairs()` is reused by steps 3 and 8.

**Run.** `python 01_rules_rapidfuzz.py` from `er-demo/` (needs `data/customers.csv`; `run_all.sh` creates it first).

**Reads / Writes.** Reads `data/customers.csv`. Writes `results/clusters_rapidfuzz.csv` (record to cluster), `results/review_queue_rapidfuzz.csv` (grey-zone pairs) and `results/metrics_rapidfuzz.csv` (one metrics row, collected by `09_compare.py`).

**Slides.** 4 (pipeline), 7 (blocking), 8 (three ways to score a pair), 13 (precision or recall), and 15 (why pair scores lie) for the chaining effect of Union-Find.

**Guide.** [3.2 Standardisation](DEMO_GUIDE.md#32-standardisation), [3.3 Blocking](DEMO_GUIDE.md#33-blocking-indexing), [3.4 Comparing and scoring](DEMO_GUIDE.md#34-comparing-and-scoring), [3.9 Matching-quality metrics](DEMO_GUIDE.md#39-matching-quality-metrics), [Code tour 1](DEMO_GUIDE.md#1-hand-built-matcher-01_rules_rapidfuzzpy).

### Walkthrough

1. [01_rules_rapidfuzz.py#L1-L20](01_rules_rapidfuzz.py#L1-L20) **Module docstring.** The five stages of the classic matcher (standardise, block, score, threshold, cluster), plus inputs, outputs and slides. Slide 4 shows the same pipeline.
2. [01_rules_rapidfuzz.py#L22-L48](01_rules_rapidfuzz.py#L22-L48) **Imports.** `itertools.combinations` builds every pair inside a block; `rapidfuzz.fuzz` gives string similarities on 0..100. The `sys.path` line makes the shared [common/evaluate.py](common/evaluate.py) (`blocking_recall`, `evaluate_clusters`, `union_find_clusters`) and [common/standardise.py](common/standardise.py) (`standardise`) importable. Every matcher uses the same cleaning and the same metrics, which is what makes the comparison fair.
3. [01_rules_rapidfuzz.py#L50-L54](01_rules_rapidfuzz.py#L50-L54) **Thresholds.** `AUTO_MATCH = 0.80` and `REVIEW = 0.65` create three bands. Only the top band creates edges; the middle band is work for a data steward. Moving these numbers is the precision/recall trade-off of slide 13.
4. [01_rules_rapidfuzz.py#L56-L70](01_rules_rapidfuzz.py#L56-L70) **`BLOCKING_KEYS`.** Five alternative keys: email, phone, DOB + surname sound, postcode + first-name sound, canonical first name + surname. A multi-column key requires all columns to be equal. The keys are unioned, so a pair missed by one (say, a missing email) can be found by another. This is slide 7.
5. [01_rules_rapidfuzz.py#L73-L92](01_rules_rapidfuzz.py#L73-L92) **`candidate_pairs()`.** For each key: drop records with an empty key value (otherwise all blanks form one giant block), group by the key, and add every pair inside each block. Blocks of more than 200 records are skipped because a block of n records costs n(n-1)/2 comparisons and huge blocks usually come from shared generic values. Pairs are sorted so (a, b) and (b, a) are the same tuple, and the set removes pairs found by several keys. Result: 6,405 pairs instead of 33.5 million (slide 7).
6. [01_rules_rapidfuzz.py#L95-L103](01_rules_rapidfuzz.py#L95-L103) **`sim()`.** Returns `None` when either value is missing (no evidence, not disagreement), otherwise the RapidFuzz score divided by 100. `fuzz.ratio` is a normalised edit-distance similarity; the caller can pass another function, such as `token_set_ratio`.
7. [01_rules_rapidfuzz.py#L106-L155](01_rules_rapidfuzz.py#L106-L155) **`score()`.** Seven fields, each a (similarity, weight) tuple with weights summing to 1.0. Names, email and address are fuzzy; DOB, phone and postcode are exact (1.0 or 0.0), and `None` when either side is missing. Lines [L147-L155](01_rules_rapidfuzz.py#L147-L155) drop missing fields and divide by the weights still in play, so a WEB record without address or DOB is not punished for having less data. The weights are guesses, which is exactly the weakness that Fellegi-Sunter fixes (slide 8, "weighted fuzzy score" row).
8. [01_rules_rapidfuzz.py#L158-L172](01_rules_rapidfuzz.py#L158-L172) **Load, clean, block.** `standardise()` normalises names, emails, phones and postcodes and adds the derived keys. `by_id` is an index for fast record lookup. `blocking_recall()` uses the synthetic truth only to measure how many true pairs survived blocking (the ceiling on recall).
9. [01_rules_rapidfuzz.py#L174-L182](01_rules_rapidfuzz.py#L174-L182) **Score and band.** Every candidate pair is scored, turned into a DataFrame, and split into `matches` (>= 0.80) and `review` (0.65 to 0.80).
10. [01_rules_rapidfuzz.py#L184-L194](01_rules_rapidfuzz.py#L184-L194) **Cluster and evaluate.** `union_find_clusters()` takes connected components over the auto-match edges, so A-B plus B-C puts A, B and C together even if A-C was never compared. This transitivity is why one bad edge can merge two people (slide 15). `evaluate_clusters()` returns pair and B-cubed precision/recall/F1, the largest cluster, false-merge pairs and missed pairs.
11. [01_rules_rapidfuzz.py#L196-L206](01_rules_rapidfuzz.py#L196-L206) **Save.** Clusters, review queue and a one-row metrics table tagged `rules + rapidfuzz`.
12. [01_rules_rapidfuzz.py#L209-L212](01_rules_rapidfuzz.py#L209-L212) **Entry point.** `main()` runs only when the file is executed directly, so `03_ml_recordlinkage.py` and `08_mlops_feature_store.py` can import `candidate_pairs()` without running the matcher.

### What you should see

```
blocking: {'candidate_pairs': 6405, 'pair_completeness': 0.9649, 'reduction_ratio': 0.999809}
auto-matches: 5300, review queue: 334
quality: {'pair_precision': 0.9523, 'pair_recall': 0.9127, 'pair_f1': 0.9321, 'bcubed_precision': 0.9882, 'bcubed_recall': 0.9539, 'bcubed_f1': 0.9707, 'n_records': 8192, 'n_pred_entities': 4278, 'n_true_entities': 4000, 'largest_cluster': 9, 'false_merges_pairs': 267, 'missed_pairs': 510}
```

How to read it:
- **Blocking**: 6,405 candidate pairs out of about 33.5 million possible (reduction ratio 99.98%). Pair completeness 0.9649 means 96.5% of the true pairs are among the candidates, so no matcher in this demo can exceed that pair recall.
- **Bands**: 5,300 pairs became edges and 334 would go to a steward.
- **Quality**: pair precision 0.952 with **267 false-merge pairs**, pair recall 0.913 with **510 missed pairs**. 4,278 predicted customers against 4,000 real ones means the matcher under-merges (it splits people), while the largest cluster of 9 records shows some chaining. These are the weakest numbers of the three matchers, the starting point of the results chart (slide 27).

### Try this

1. **Raise `AUTO_MATCH` to 0.90** ([L54](01_rules_rapidfuzz.py#L54)). Fewer edges: false merges drop, missed pairs rise and `n_pred_entities` grows. Lower it to 0.70 and the opposite happens, with a larger `largest_cluster`. This is slide 13 in practice.
2. **Remove the `["email"]` key** from `BLOCKING_KEYS` ([L61](01_rules_rapidfuzz.py#L61)). Candidate pairs and pair completeness both fall; recall cannot recover however you tune the scoring, because blocking is a ceiling.
3. **Change a weight**, for example give `"postcode"` 0.20 and `"email"` 0.05 ([L127](01_rules_rapidfuzz.py#L127), [L141](01_rules_rapidfuzz.py#L141)). Household members (same address and postcode) start to merge, which shows how sensitive hand-picked weights are.

---

## 02_splink.py

**What it does.** The probabilistic matcher. It describes a Fellegi-Sunter model to Splink (blocking rules plus seven field comparisons, each a ladder of levels), trains it without any labels (prior, then `u` from random pairs, then `m` with three EM sessions), scores the candidate pairs, and clusters at p >= 0.95. It also sweeps several thresholds, saves the trained model as JSON for the later steps, and writes three charts that make the weights visible.

**Run.** `python 02_splink.py` from `er-demo/` (runs locally on DuckDB; the Databricks version swaps in `SparkAPI`, see [databricks/splink_on_databricks.py](databricks/splink_on_databricks.py)).

**Reads / Writes.** Reads `data/customers.csv`. Writes to `results/`: `splink_model.json` (reused by `05_mdm.py`, `06_customer_spine.py`, `07_identity_drift.py`), `pairs_splink.csv` (read by `04_graph_resolution.py`), `clusters_splink.csv`, `review_queue_splink.csv`, `splink_threshold_sweep.csv`, `splink_match_weights.html`, `splink_m_u_parameters.html`, `splink_waterfall_example.html`, `metrics_splink.csv`.

**Slides.** 7 (blocking), 8 (three ways to score), **9 (fields, levels, m and u)**, **10 (adding up bits: Robert Smith vs Bob Smyth)**, 13 (precision or recall).

**Guide.** [3.5 Fellegi-Sunter, step by step](DEMO_GUIDE.md#35-fellegi-sunter-step-by-step), in particular [Step 7](DEMO_GUIDE.md#step-7-add-everything-up-and-convert-to-a-probability) and [Step 8](DEMO_GUIDE.md#step-8-how-the-model-learns-m-and-u-without-labels); [3.3 Blocking](DEMO_GUIDE.md#33-blocking-indexing); [Code tour 2](DEMO_GUIDE.md#2-probabilistic-matcher-02_splinkpy).

### The model in five lines (slides 9 and 10)

- **Fields and levels.** Each of the seven fields is compared on a ladder of levels, for example surname: exact, Jaro-Winkler >= 0.92, >= 0.88, >= 0.70, all other, plus a "missing" level. A pair lands on the first level that is true.
- **m** = how often *true matches* land on that level (data quality). First name exact: m = 0.676.
- **u** = how often *different people* land on it by coincidence (how common the value is). First name exact: u = 0.0047.
- **Bits.** Each level adds log2(m / u) bits: first name exact is log2(0.676 / 0.0047) = +7.2. Missing adds 0.
- **Prior.** Every pair starts at log2(λ / (1 − λ)) with λ ≈ 0.00022, which is −12.1 bits. Total weight w = prior + field bits, probability = 2^w / (1 + 2^w). Slide 10: Robert Smith vs Bob Smyth gets −12.1 + 7.2 (first name) + 5.3 (surname JW >= 0.88) + 12.3 (email) − 1.8 (postcode) = **+10.9 bits, p ≈ 0.9995**.

### Walkthrough

1. [02_splink.py#L1-L33](02_splink.py#L1-L33) **Module docstring.** The model in brief, every output file and which later step reads it, slides, and an explanation of the expected warnings (see "What you should see").
2. [02_splink.py#L35-L55](02_splink.py#L35-L55) **Imports.** `splink.comparison_library` (`cl`) holds the ready-made comparison ladders. `DuckDBAPI` is the SQL backend, `Linker` the object that trains, predicts, clusters and draws, `SettingsCreator` the model specification and `block_on` the blocking-rule helper. The shared cleaning and metrics are the same as in steps 1 and 3.
3. [02_splink.py#L57-L60](02_splink.py#L57-L60) **`CLUSTER_THRESHOLD = 0.95`.** The match probability a pair needs to become an edge. It is a business choice, explored by the sweep below.
4. [02_splink.py#L62-L81](02_splink.py#L62-L81) **`MODEL_COLUMNS`.** The columns loaded into DuckDB: record ID, compared fields, blocking keys, and `true_entity_id`, which is carried only so the clusters can be evaluated; no rule or comparison uses it.
5. [02_splink.py#L83-L97](02_splink.py#L83-L97) **Settings: task and blocking.** `dedupe_only` because all sources are already in one table. The five prediction blocking rules are the same keys as step 1, so all matchers compare the same kind of candidates (slide 7).
6. [02_splink.py#L98-L123](02_splink.py#L98-L123) **Settings: comparisons (slide 9).** The seven fields and their level ladders: `NameComparison` for first name and surname with term-frequency adjustment (agreeing on a rare name is worth more bits than agreeing on "smith"), `DateOfBirthComparison` (exact, Levenshtein <= 1, within 1 month / 1 year / 10 years), `EmailComparison` (exact, same username, fuzzy), exact phone, `PostcodeComparison` (full, sector, district, area) and Jaro-Winkler address. Each level of each ladder will get its own m, u and weight. `retain_intermediate_calculation_columns=True` keeps the per-field levels in the predictions so the waterfall chart can show them.
7. [02_splink.py#L126-L134](02_splink.py#L126-L134) **`build_linker()`.** Creates an in-memory DuckDB database, registers the selected columns as table `customers`, and builds the `Linker`. `log_level=logging.WARNING` hides Splink's routine info messages but still shows warnings.
8. [02_splink.py#L137-L176](02_splink.py#L137-L176) **`train()`: three stages, no labels.**
   - [L139-L152](02_splink.py#L139-L152) **Prior.** `estimate_probability_two_random_records_match` counts pairs that pass three strict rules (same email, same phone, same full name and DOB), assumes those rules find 70% of the true matches (`recall=0.7`) and divides by the number of possible pairs. Result: λ ≈ 0.00022, the −12.1 bits every pair starts from (slide 10).
   - [L153-L157](02_splink.py#L153-L157) **u.** `estimate_u_using_random_sampling` samples up to 2 million random pairs. Random pairs are almost never the same person, so the share landing on each level *is* u.
   - [L158-L176](02_splink.py#L158-L176) **m with EM, three sessions.** EM guesses m, scores the pairs inside a training block, re-estimates m from those probabilities and repeats until stable. Inside a block on DOB every pair agrees on DOB, so that session cannot learn DOB's m (Splink fixes it). Hence three sessions: blocked on DOB (learns everything but DOB), on postcode (learns DOB, not postcode), on first name + surname (learns DOB, postcode, email, phone, address). Splink averages each field's m over the sessions that could learn it, so every field is covered at least once. This is the "how it learns without labels" of [Step 8](DEMO_GUIDE.md#step-8-how-the-model-learns-m-and-u-without-labels).
9. [02_splink.py#L179-L188](02_splink.py#L179-L188) **Load, build, train.** Same input and cleaning as step 1; the truth column is never touched during training.
10. [02_splink.py#L190-L195](02_splink.py#L190-L195) **Predict.** Scores every candidate pair (prior + bits, converted to a probability) and keeps pairs with p >= 0.2, so the review band and the sweep can reuse one scored set. The "m values not fully trained" warning is printed here.
11. [02_splink.py#L196-L205](02_splink.py#L196-L205) **Cluster at 0.95 and evaluate.** `cluster_pairwise_predictions_at_threshold` keeps edges with p >= 0.95 and takes connected components; `as_pandas_dataframe()` brings the result back from DuckDB. Metrics use the same `evaluate_clusters()` as step 1.
12. [02_splink.py#L207-L235](02_splink.py#L207-L235) **Threshold sweep (slide 13).** Re-clusters the same predictions at 0.5 to 0.999 without retraining and prints precision, recall, F1, B-cubed F1 and the number of predicted customers for each.
13. [02_splink.py#L237-L248](02_splink.py#L237-L248) **Save the model and the weight charts.** `save_model_to_json` writes the settings, prior and every m and u, so later steps score new data without retraining. `match_weights_chart` shows log2(m / u) per level (the bits of slides 9 and 10); `m_u_parameters_chart` shows raw m and u side by side.
14. [02_splink.py#L249-L260](02_splink.py#L249-L260) **Pairs and review queue.** All scored pairs with `match_weight` and `match_probability` go to `pairs_splink.csv` (the weighted edges for step 4). Pairs with 0.5 <= p < 0.95 form the review queue.
15. [02_splink.py#L261-L269](02_splink.py#L261-L269) **Waterfall chart (slide 10).** Picks the pair one third of the way up the probability ranking and draws the prior bar, one bar per field (missing fields shown as 0 because `filter_nulls=False`), and the final weight. It is slide 10 for a real pair.
16. [02_splink.py#L270-L276](02_splink.py#L270-L276) **Save clusters, sweep and metrics** (method tag `splink (EM, p>=0.95)`, collected by `09_compare.py`).

### What you should see

First the training warnings:

```
WARNING:
Level Exact match on sector on comparison postcode not observed in dataset, unable to train m value
WARNING:
Level Exact match on district on comparison postcode not observed in dataset, unable to train m value
WARNING:
Level Levenshtein distance <= 1 on comparison dob not observed in dataset, unable to train m value
...
 -- WARNING --
You have called predict(), but there are some parameter estimates which have neither been estimated or specified ...
Comparison: 'dob':
    m values not fully trained
Comparison: 'postcode':
    m values not fully trained
```

**These are expected.** EM can only estimate m for a level if some likely matches land on it. In the synthetic data a DOB error is a day-month swap (two or more character edits, never one), and a person who moves gets a completely new random postcode, so no true match ever agrees on only the postcode sector or district. Each EM session that could learn DOB or postcode reports the missing level (DOB in sessions 2 and 3, postcode in sessions 1 and 3), and `predict()` then reminds you that those levels fall back to default m values. In `results/splink_model.json` these three levels have a u but no m. They are rare for non-matches too, so the effect on scores is negligible. On real data, where these patterns occur, the warnings would disappear.

Then the results:

```
quality @ 0.95 {'pair_precision': 0.9661, 'pair_recall': 0.9649, 'pair_f1': 0.9655, 'bcubed_precision': 0.9902, 'bcubed_recall': 0.9804, 'bcubed_f1': 0.9853, 'n_records': 8192, 'n_pred_entities': 4102, 'n_true_entities': 4000, 'largest_cluster': 7, 'false_merges_pairs': 198, 'missed_pairs': 205}
 threshold  pair_precision  pair_recall  pair_f1  bcubed_f1  n_pred_entities
     0.500          0.9429       0.9752   0.9588     0.9845             4033
     0.800          0.9576       0.9699   0.9637     0.9852             4070
     0.900          0.9611       0.9678   0.9644     0.9851             4084
     0.950          0.9661       0.9649   0.9655     0.9853             4102
     0.990          0.9759       0.9629   0.9693     0.9862             4121
     0.999          0.9813       0.9512   0.9660     0.9840             4172
review queue (0.5 <= p < 0.95): 161 pairs
```

How to read it:
- At 0.95, pair precision 0.966 with **198 false-merge pairs** and recall 0.965 with **205 missed pairs**, against 267 / 510 for the rules matcher, without a single label. Recall almost reaches the blocking ceiling (0.9649).
- The sweep is slide 13: as the threshold rises, precision goes up (0.943 to 0.981), recall goes down (0.975 to 0.951) and the number of predicted customers grows (more splitting).
- Many remaining false merges are household members: shared surname, address, postcode and family email really are strong evidence (Example B in [Step 7](DEMO_GUIDE.md#step-7-add-everything-up-and-convert-to-a-probability)). Step 4 removes most of them with a cannot-link rule.
- Open `results/splink_match_weights.html` and `results/splink_waterfall_example.html` to see the bits of slides 9 and 10.

### Try this

1. **Change `CLUSTER_THRESHOLD` to 0.99** ([L60](02_splink.py#L60)). The headline metrics move to the 0.990 row of the sweep, and the review queue (0.5 <= p < 0.99) grows.
2. **Remove the postcode EM session** ([L168-L170](02_splink.py#L168-L170)). DOB is then learned only in session 3; compare the DOB rows of `splink_m_u_parameters.html` before and after.
3. **Set `recall=0.9`** in the prior estimate ([L151](02_splink.py#L151)). λ becomes smaller, so every pair starts with fewer bits; probabilities fall slightly and borderline pairs drop below 0.95.

---

## 03_ml_recordlinkage.py

**What it does.** The supervised matcher. It reuses step 1's blocking, turns every candidate pair into a row of 14 numeric features (string similarities, exact and phonetic agreement, and a whole-record TF-IDF cosine), labels each pair from the synthetic truth, and trains a gradient boosting classifier with two-fold cross-fitting so every pair gets an out-of-fold probability. Pairs above 0.9 become edges, and connected components become customers.

**Run.** `python 03_ml_recordlinkage.py` from `er-demo/`.

**Reads / Writes.** Reads `data/customers.csv` (and imports `candidate_pairs()` from `01_rules_rapidfuzz.py`). Writes `results/pairs_ml_features.csv` (features, label and `ml_probability` per pair, read by `04_graph_resolution.py`) and `results/metrics_ml.csv` (collected by `09_compare.py`). `08_mlops_feature_store.py` imports `features()` from this file.

**Slides.** 8 (three ways to score), 11 (supervised features), 12 (labels), 13 (precision or recall), 15 (why pair scores lie).

**Guide.** [3.6 Supervised matching, step by step](DEMO_GUIDE.md#36-supervised-matching-step-by-step), especially [Step 2. Features](DEMO_GUIDE.md#step-2-features-turn-a-pair-into-a-row-of-numbers) and [Step 5. Evaluate without fooling yourself](DEMO_GUIDE.md#step-5-evaluate-without-fooling-yourself); [Code tour 3](DEMO_GUIDE.md#3-supervised-matcher-03_ml_recordlinkagepy).

### Walkthrough

1. [03_ml_recordlinkage.py#L1-L21](03_ml_recordlinkage.py#L1-L21) **Module docstring.** Indexing, features and model in brief, the honest caveat about the fold split, outputs and slides.
2. [03_ml_recordlinkage.py#L23-L47](03_ml_recordlinkage.py#L23-L47) **Imports.** `recordlinkage.Compare` computes one similarity column per comparison. `HistGradientBoostingClassifier` is a fast gradient-boosted tree model that accepts NaN, so missing fields need no imputation. `TfidfVectorizer` builds the character n-gram vectors, `average_precision_score` the threshold-free ranking metric.
3. [03_ml_recordlinkage.py#L49-L55](03_ml_recordlinkage.py#L49-L55) **Reuse blocking and set the threshold.** `__import__("01_rules_rapidfuzz")` is needed because a module name starting with a digit cannot appear in an `import` statement. Reusing `candidate_pairs()` guarantees the same 6,405 pairs as step 1, so differences come from the scoring alone. `THRESHOLD = 0.9` is the operating point.
4. [03_ml_recordlinkage.py#L58-L69](03_ml_recordlinkage.py#L58-L69) **`record_text()`.** Joins first name, surname, email username, postcode and address into one string per record (missing values become empty strings). This "whole record" view feeds the TF-IDF feature.
5. [03_ml_recordlinkage.py#L72-L119](03_ml_recordlinkage.py#L72-L119) **`features()`: field comparisons (slide 11).** Thirteen columns per pair: Jaro-Winkler on first name, Jaro-Winkler and Levenshtein on surname, exact Metaphone codes for both names (sound-alike agreement), exact and Levenshtein DOB (the second gives partial credit for a day-month swap), q-gram email, Jaro-Winkler email username, exact phone, postcode and postcode area, and q-gram address. `missing_value=np.nan` keeps "unknown" separate from "different". Several overlapping similarities on one field are deliberate: the model learns which ones matter and how they interact, which hand-picked weights (step 1) and independent field weights (step 2) cannot.
6. [03_ml_recordlinkage.py#L121-L139](03_ml_recordlinkage.py#L121-L139) **`features()`: whole-record TF-IDF cosine.** Fits a character 2-4-gram TF-IDF vectorizer (only when none is passed, so serving in step 8 reuses the training vocabulary), turns each record into a sparse normalised vector, maps pair IDs to matrix rows, and takes the row-wise dot product, which equals the cosine similarity. It is a cheap "embedding" that tolerates typos and fields in the wrong column.
7. [03_ml_recordlinkage.py#L142-L151](03_ml_recordlinkage.py#L142-L151) **Load, block, featurise.** The table is indexed by `unique_id` because `recordlinkage` looks records up by index; `reset_index()` gives `candidate_pairs()` back the column it expects. Sorting makes the pair order reproducible.
8. [03_ml_recordlinkage.py#L152-L158](03_ml_recordlinkage.py#L152-L158) **Labels (slide 12).** A pair is 1 when both records share `true_entity_id`, else 0. In production these labels would come from steward decisions on the review queue. The truth is a label, never a feature.
9. [03_ml_recordlinkage.py#L160-L179](03_ml_recordlinkage.py#L160-L179) **Two-fold cross-fitting.** Pairs are split by the parity of the left record's entity ID; each fold is scored by a model trained on the other, so every probability is out of fold. It is not strictly entity-disjoint (the same person can appear on the right side of a training pair), which is why step 8 repeats the test with a strict split. Prints pairs, positives and average precision.
10. [03_ml_recordlinkage.py#L181-L191](03_ml_recordlinkage.py#L181-L191) **Thresholds after clustering (slides 13 and 15).** For 0.5, 0.9 and 0.99 the script builds connected components and prints cluster-level precision, recall and largest cluster. A near-perfect pair ranking can still produce false merges once edges chain.
11. [03_ml_recordlinkage.py#L193-L199](03_ml_recordlinkage.py#L193-L199) **Final clustering at 0.9** and full metrics with the same `evaluate_clusters()` as steps 1 and 2.
12. [03_ml_recordlinkage.py#L201-L215](03_ml_recordlinkage.py#L201-L215) **Save.** Features plus `label` and `ml_probability` per pair (the pair MultiIndex becomes columns `id_l`, `id_r`), and a one-row metrics table.

### What you should see

```
pairs: 6405, positives: 5639, average precision (out of fold): 0.9998
  threshold 0.5: pair P=0.9683 R=0.9762 largest cluster=9
  threshold 0.9: pair P=0.9757 R=0.9752 largest cluster=7
  threshold 0.99: pair P=0.9805 R=0.9735 largest cluster=7
quality: {'pair_precision': 0.9757, 'pair_recall': 0.9752, 'pair_f1': 0.9754, 'bcubed_precision': 0.9937, 'bcubed_recall': 0.9858, 'bcubed_f1': 0.9898, 'n_records': 8192, 'n_pred_entities': 4082, 'n_true_entities': 4000, 'largest_cluster': 7, 'false_merges_pairs': 142, 'missed_pairs': 145}
```

How to read it:
- 5,639 of the 6,405 candidate pairs are true matches; the rest are hard negatives that blocking proposed.
- Average precision 0.9998 says the ranking of pairs is almost perfect, yet the clusters still contain **142 false-merge pairs**. Pair scores flatter the model; cluster metrics are the honest ones (slide 15).
- At 0.9: pair precision 0.976, recall 0.975 and **145 missed pairs**, the best of the three matchers (rules 267 / 510, Splink 198 / 205), but it needed labels.
- The threshold lines show slide 13 again: 0.5 to 0.99 raises precision and lowers recall, and the lowest threshold has the largest cluster (9) because more weak edges chain.

### Try this

1. **Change `THRESHOLD` to 0.99** ([L55](03_ml_recordlinkage.py#L55)). The final metrics match the `threshold 0.99` line: fewer false merges, slightly more missed pairs.
2. **Drop the TF-IDF feature** by commenting out [L138](03_ml_recordlinkage.py#L138). Compare average precision and the false-merge count with the baseline: the field features carry most of the signal on this clean synthetic data, while on messier free text the whole-record cosine usually matters more.
3. **Replace the fold rule** at [L164](03_ml_recordlinkage.py#L164) with a random split (for example `np.random.default_rng(0).integers(0, 2, len(X))`). Expect slightly more optimistic scores, because the same people appear in training and test, the leakage that step 8's entity-disjoint split avoids.

---

## 04_graph_resolution.py

**What it does.** Turns the accepted pairs from the Splink matcher (02) and the supervised matcher (03) into a record graph, where records are nodes and accepted matches are edges weighted by evidence in bits. A customer is a connected component. Components that contain two records which business rules say cannot be the same person (conflicting DOBs, clearly different first names) are split with a weighted minimum cut. Finally it lists emails and phones that point at more than one resolved customer.

**Run.** `python 04_graph_resolution.py` (from `er-demo/`, after `02_splink.py` and `03_ml_recordlinkage.py`).

**Reads / Writes.**
- Reads `data/customers.csv`, `results/pairs_splink.csv`, `results/pairs_ml_features.csv`.
- Writes `results/metrics_graph.csv` (one row per edge source after repair), `results/clusters_graph.csv` (repaired Splink clusters, the input of `05_mdm.py`), `results/shared_identifiers.csv` (the steward work queue).

**Slides.** 14, 15, 16, 17, 27.

**Guide.** [3.7 Clustering and the graph view](DEMO_GUIDE.md#37-clustering-and-the-graph-view-step-by-step), in particular [Step 3. Chaining](DEMO_GUIDE.md#step-3-chaining-why-one-bad-edge-is-enough), [Step 4. Cannot-link constraints](DEMO_GUIDE.md#step-4-cannot-link-constraints-business-knowledge-the-model-lacks), [Step 5. Minimum cut](DEMO_GUIDE.md#step-5-minimum-cut-remove-the-weakest-edges-that-separate-them) and [Step 6. The identifier graph](DEMO_GUIDE.md#step-6-the-identifier-graph-who-shares-an-email); code tour [4. Graph resolution](DEMO_GUIDE.md#4-graph-resolution-04_graph_resolutionpy); [3.9 Matching-quality metrics](DEMO_GUIDE.md#39-matching-quality-metrics) for P, R, B-cubed.

### Walkthrough

1. [04_graph_resolution.py#L1-L37](04_graph_resolution.py#L1-L37) **Module docstring.** States the idea (pairs answer "do these two match?", customers are a graph question), the five steps, inputs, outputs and run order. Slide 14.
2. [04_graph_resolution.py#L40-L58](04_graph_resolution.py#L40-L58) **Imports.** `networkx` supplies the graph, components and min cut; `rapidfuzz.distance.JaroWinkler.similarity` returns a score in [0, 1] that rewards a shared prefix, good for first names. The shared `standardise()` and `evaluate_clusters()` keep this step comparable with every other matcher.
3. [04_graph_resolution.py#L61-L66](04_graph_resolution.py#L61-L66) **Constants.** Edges are pairs with Splink p >= 0.95 or ML p >= 0.9, the same thresholds 02 and 03 cluster at, so "before repair" reproduces their results exactly. `FIRST_NAME_CONFLICT = 0.75` is the Jaro-Winkler level below which two canonical first names count as different people.
4. [04_graph_resolution.py#L69-L79](04_graph_resolution.py#L69-L79) **`dob_conflict()`.** A conflict needs both DOBs known and different. A same-year day/month swap (03/04 vs 04/03) is treated as a typo, not a different person. Why: a missing value is no evidence of difference, and swaps are the most common DOB error. Slide 16 (constraint), slide 17 (Thomas 2008-07-14 vs Stanley 2002-07-12).
5. [04_graph_resolution.py#L82-L97](04_graph_resolution.py#L82-L97) **`name_conflict()`.** Fires only when nothing else explains different first names: not when they sound alike (same metaphone), not when the DOB matches (a nickname typo), not when a first name looks like the other record's last name (fields swapped, Jaro-Winkler >= 0.85). Otherwise Jaro-Winkler < 0.75 means different people. These exceptions keep the rule from splitting genuine matches. Slide 16.
6. [04_graph_resolution.py#L100-L103](04_graph_resolution.py#L100-L103) **`cannot_link()`.** Either rule is a hard business constraint that overrules any model score. Slide 16.
7. [04_graph_resolution.py#L106-L117](04_graph_resolution.py#L106-L117) **`evidence_bits()`.** Converts an ML probability to log-odds in bits, `log2(p / (1 - p))`, the same scale as Splink's `match_weight`. Probabilities saturate near 1.0, bits do not, so the min cut can tell a 15-bit edge from a 60-bit one. Clamping keeps the log finite; the 0.01 floor keeps capacities positive. Slide 17 ("why bits").
8. [04_graph_resolution.py#L120-L130](04_graph_resolution.py#L120-L130) **`build_graph()`.** Adds every record as a node (so unmatched records are singleton customers) and every accepted pair as an undirected edge with `weight` = bits. Slide 14.
9. [04_graph_resolution.py#L133-L181](04_graph_resolution.py#L133-L181) **`repair()`.** The core of the step. It queues every multi-record component ([L141](04_graph_resolution.py#L141)), looks for the first cannot-link pair inside it ([L151-L158](04_graph_resolution.py#L151-L158)), and skips components with none. For a conflicting component it copies the subgraph, sets each edge's `capacity` to its bits ([L163-L167](04_graph_resolution.py#L163-L167)), and calls `nx.minimum_cut(sub, a, b)`, which returns the cheapest partition that separates the two conflicting records ([L172](04_graph_resolution.py#L172)). The edges crossing the partition are removed ([L174-L178](04_graph_resolution.py#L174-L178)) and both pieces go back on the queue ([L180](04_graph_resolution.py#L180)), because one cut can leave another conflict behind. Why it matters: it removes the weakest links (a family email, a shared address) and keeps the strong ones. Slides 16 and 17 (cut 1 removes the two 6.6-bit edges, cut 2 the four 15.3 and 25.3-bit edges, the 59.5-bit edge is never cut).
10. [04_graph_resolution.py#L184-L187](04_graph_resolution.py#L184-L187) **`to_clusters()`.** Turns components into `{record_id: cluster_id}`, using the smallest member id as a deterministic label.
11. [04_graph_resolution.py#L190-L213](04_graph_resolution.py#L190-L213) **`shared_identifiers()`.** The identifier graph: for each email and phone value, count how many distinct resolved customers its records belong to; more than one is flagged. `truly_shared` uses the synthetic truth only to evaluate the list. Why: a really shared value (family mailbox) should be excluded from blocking; the rest point at missed matches. Slide 16 ("Flag").
12. [04_graph_resolution.py#L216-L235](04_graph_resolution.py#L216-L235) **`main()`, loading.** Re-standardises the raw data indexed by `unique_id`, keeps accepted Splink pairs (renaming `match_weight` to `bits`) and accepted ML pairs (adding `bits` via `evidence_bits`).
13. [04_graph_resolution.py#L238-L257](04_graph_resolution.py#L238-L257) **`main()`, before and after.** For each edge source: build the graph, evaluate plain connected components ("before", identical to 02 / 03), repair, evaluate again ("after"), print the stats and both metric lines. Slides 16 and 27.
14. [04_graph_resolution.py#L260-L265](04_graph_resolution.py#L260-L265) **Shared-identifier summary.** Built on the repaired Splink clusters, the ones MDM uses next.
15. [04_graph_resolution.py#L269-L274](04_graph_resolution.py#L269-L274) **Outputs.** Metrics for `09_compare.py`, `clusters_graph.csv` for `05_mdm.py`, the shared-identifier CSV.
16. [04_graph_resolution.py#L278-L279](04_graph_resolution.py#L278-L279) Standard entry point.

### What you should see

```text
splink: {'components_checked': 2712, 'components_split': 42, 'edges_cut': 80}
  connected components   P=0.9661 R=0.9649 B3-F1=0.9853 false-merge pairs=198
  + graph repair         P=0.9979 R=0.9617 B3-F1=0.9889 false-merge pairs=12
ml: {'components_checked': 2714, 'components_split': 26, 'edges_cut': 36}
  connected components   P=0.9757 R=0.9752 B3-F1=0.9898 false-merge pairs=142
  + graph repair         P=0.9984 R=0.9723 B3-F1=0.9918 false-merge pairs=9
shared identifiers flagged: 73, of which really shared by different people: 31
```

How to read it:
- `components_checked` counts every component examined, including the new pieces re-queued after a cut. For Splink 42 components held a conflict and 80 edges were cut.
- The "connected components" line equals the 02 (Splink) and 03 (ML) results; the "+ graph repair" line is the improvement. Splink false-merge pairs drop from 198 to 12 while recall drops only from 0.965 to 0.962. ML drops from 142 to 9, and its B-cubed F1 of 0.9918 is the best in the demo (slide 27: 0.992).
- After repair Splink has 4,144 customers and ML 4,108 (in `metrics_graph.csv`); the largest cluster falls to 6, the real maximum in the generator.
- The 73 shared identifiers are 48 emails and 25 phones. 31 emails are real family mailboxes; the other 17 emails and all 25 phones belong to one person split across two customers, i.e. missed matches for a steward.

### Try this

1. Set `FIRST_NAME_CONFLICT = 0.85` (line 66). More name pairs count as conflicts, so more components split: false merges fall a little further but recall drops, because genuine typo'd first names get cut apart.
2. Drop the day/month swap exception: replace line 79 with `return True`. Every different DOB becomes a conflict, so a few real people with swapped DOBs get split. Recall falls slightly for almost no precision gain.
3. Change `SPLINK_THRESHOLD` to 0.8 (line 65). The graph gets more, weaker edges, so "before" precision falls and more components hold conflicts; repair recovers much of it, which shows constraints and min cut let you run a lower threshold safely.

---

## 05_mdm.py

**What it does.** Builds a small master data management (MDM) hub in a DuckDB file. It seeds the hub from the batch clusters of the earlier matchers (one master `customer_id` per cluster), builds a golden record per customer with field-level survivorship and provenance, then matches a new batch of records against the master with the saved Splink model: confident matches are attached, grey-zone matches go to a review queue, and the rest become new customers. Finally it shows a data-steward approval and a GDPR erasure, and exports the main tables.

**Run.** `python 05_mdm.py` from `er-demo/`, after `02_splink.py` (writes `results/splink_model.json` and `results/clusters_splink.csv`) and preferably `04_graph_resolution.py` (writes `results/clusters_graph.csv`).

**Reads / Writes.**
- Reads: `data/customers.csv`, `data/new_batch.csv`, `results/clusters_graph.csv` (falls back to `results/clusters_splink.csv`), `results/splink_model.json`.
- Writes: `results/mdm.duckdb` (tables `source_record`, `xref`, `golden_record`, `golden_history`, `review_queue`, `steward_audit`, sequence `customer_seq`), `results/mdm_golden_record.csv`, `results/mdm_xref.csv`, `results/mdm_review_queue.csv`. The DuckDB file is deleted and recreated on every run. `06_customer_spine.py` reads the DuckDB file, not the CSVs.

**Slides.** 18 (Section Mastering), 19 (Mini MDM), 13 (Precision or recall: the two thresholds), 9 (term-frequency adjustments reused at scoring time), 16 (cannot-link repaired clusters as the seed), 20 (the spine built on top of this hub).

**Guide.** [3.8 MDM, golden record and customer spine](DEMO_GUIDE.md#38-mdm-golden-record-and-customer-spine), [3.9 Matching-quality metrics](DEMO_GUIDE.md#39-matching-quality-metrics), [Code tour step 5](DEMO_GUIDE.md#5-master-data-workflow-05_mdmpy), [6. Optional: demonstrate un-merge](DEMO_GUIDE.md#6-optional-demonstrate-un-merge).

### Walkthrough

1. [05_mdm.py#L1-L32](05_mdm.py#L1-L32) Module docstring: the list of MDM capabilities, inputs, outputs and run order. Read it first to see the hub as a system, not a matcher (slide 19).
2. [05_mdm.py#L34-L53](05_mdm.py#L34-L53) Imports. `duckdb` is the embedded database that plays the hub; `DuckDBAPI` and `Linker` from Splink load the trained model; `standardise` is the same cleansing the matchers use, so stored values match what the model saw.
3. [05_mdm.py#L55-L104](05_mdm.py#L55-L104) Configuration. `AUTO_MATCH, REVIEW = 0.95, 0.50` (L62) split incoming records into attach, review and new (slide 13: a higher auto threshold buys precision). `GOLDEN_FIELDS` are the attributes survivorship decides. `SOURCE_PRIORITY` ranks trust (CRM over BILLING over WEB) and is only a tie-breaker. `RECENCY_FIELDS` marks contact data where the latest value wins. `MODEL_COLUMNS` is exactly what the saved Splink model expects.
4. [05_mdm.py#L107-L110](05_mdm.py#L107-L110) `now()`: one UTC ISO timestamp format for links, versions and audit rows.
5. [05_mdm.py#L116-L155](05_mdm.py#L116-L155) `MiniMDM.__init__()`: creates the six tables and the id sequence. The design point is separation: raw-but-cleansed sources, the crosswalk (`xref`, source id to master id), and the derived golden record are distinct tables, so any golden value can be traced and recomputed. `golden_history` copies the golden schema plus `valid_to` for SCD2 versioning (slide 19).
6. [05_mdm.py#L158-L163](05_mdm.py#L158-L163) `new_customer_id()`: pulls `nextval('customer_seq')` and formats `C0000001`. A sequence never reuses a value, so a master id is never recycled after a merge or erasure.
7. [05_mdm.py#L166-L225](05_mdm.py#L166-L225) `survive()`: the survivorship engine, field by field. Empty values are excluded (L179-L187). Contact fields take the most recent `updated_at`, ties broken by source trust (L188-L200). Names and DOB take the value most records agree on (case-insensitive `Counter`), then source trust, then recency (L201-L216), so a one-off typo loses to the spelling two sources share. Each winner is stored with provenance: source record, source system, rule (L217-L224). This is the "golden record with provenance" of slide 19 and guide 3.8.
8. [05_mdm.py#L227-L288](05_mdm.py#L227-L288) `rebuild_golden()`: recomputes only the touched customers. It joins `source_record` to `xref` for those ids (L235-L237), reads current versions (L239-L242), groups members per customer and runs `survive()` (L246-L266), closes the open history rows by setting `valid_to` (L267-L272), deletes and re-inserts the current golden rows, and appends the new snapshots to history (L273-L288). A customer left with no members (merged away) simply gets no new row.
9. [05_mdm.py#L290-L296](05_mdm.py#L290-L296) `_close_history()`: a helper that closes one customer's open version. Not used in the demo flow.
10. [05_mdm.py#L299-L330](05_mdm.py#L299-L330) `insert_sources()`: keeps the source columns (no truth labels), replaces email, phone, postcode and dob with their standardised form, title-cases names, stamps `loaded_at`, and bulk inserts via a registered DataFrame.
11. [05_mdm.py#L332-L339](05_mdm.py#L332-L339) `link()`: `INSERT OR REPLACE` into `xref`, so each source record has exactly one current customer, with the probability and method that put it there.
12. [05_mdm.py#L341-L372](05_mdm.py#L341-L372) `initial_load()`: stores the sources, maps every batch `cluster_id` to a new `customer_id` (cluster ids are run-specific labels, customer ids are the business key), writes the crosswalk with method `splink_batch_cluster`, and builds version 1 of every golden record.
13. [05_mdm.py#L374-L435](05_mdm.py#L374-L435) `incremental_load()`: the real-time path of an MDM. Candidate pairs are translated from existing record to existing customer (L390), only the best candidate per new record is kept (L395-L399), and then each new record is either auto-linked at p >= 0.95 (L404-L409) or given a provisional new customer (L410-L417); if the best candidate is in the 0.50 to 0.95 grey zone it is also queued for review (L418-L430). One `rebuild_golden()` call refreshes everything touched (L434). Note that review items are counted inside `new_customer` too.
14. [05_mdm.py#L438-L462](05_mdm.py#L438-L462) `approve_review()`: a steward agrees with the candidate. All records of the provisional customer are re-pointed to the target (`steward_approved`), the queue item is closed, and both customers are rebuilt: the provisional one disappears, the target gets a new version. Steward decisions are the labels that guide 3.8 says feed back into training.
15. [05_mdm.py#L464-L471](05_mdm.py#L464-L471) `reject_review()`: only changes the queue status, because the record already sits in its own customer.
16. [05_mdm.py#L473-L525](05_mdm.py#L473-L525) `unmerge_record()`: fixes a false merge for one record. It requires a reason, a known record and a customer with at least two members (L477-L494), allocates a new id, and inside a transaction moves the record, marks any review row `unmerged`, writes `steward_audit`, and rebuilds both golden records (L500-L524). Not called by `main()`; see guide section 6.
17. [05_mdm.py#L527-L552](05_mdm.py#L527-L552) `erase_customer()`: GDPR right to erasure. It finds the customer's source ids, deletes their `source_record` and `review_queue` rows, then deletes the customer from `xref`, `golden_record` and `golden_history`. Returns the number of source records removed.
18. [05_mdm.py#L555-L580](05_mdm.py#L555-L580) `score_new_records()`: loads `splink_model.json` into a `Linker` over the existing records, computes term-frequency tables for `first_name_canon`, `last_name` and `email` (rare values weigh more, slide 9), and calls `predict_between()` to score only existing-vs-new pairs that pass the model's blocking rules, keeping p >= 0.50. No retraining: the m and u values come from the saved model.
19. [05_mdm.py#L589-L609](05_mdm.py#L589-L609) `main()`, initial load: recreate the DuckDB file, read the initial data as strings, prefer the graph-repaired clusters (fewer false merges, slide 16), load, and print `(customers, records)`.
20. [05_mdm.py#L611-L617](05_mdm.py#L611-L617) Incremental batch: standardise both sides, score, apply the thresholds, print the counts.
21. [05_mdm.py#L619-L657](05_mdm.py#L619-L657) Evaluation with synthetic truth (used only after the decisions). Each pre-existing customer is labelled with the most common true person among its initial records; then `ok_link` counts returning people attached to their own customer, `should_link` counts new records whose person already existed, and `wrong_link` counts new records attached to someone else's customer (a false merge).
22. [05_mdm.py#L659-L670](05_mdm.py#L659-L670) Steward and governance demo: approve the first open review item, then erase the customer with the most source records.
23. [05_mdm.py#L672-L695](05_mdm.py#L672-L695) Exports the golden record, crosswalk and review queue to CSV, then prints one golden record with at least three sources and a phone, plus its provenance JSON (cut at 600 characters).

### What you should see

```
initial clusters from clusters_graph.csv
initial load: (4144, 8192)
incremental batch: {'auto_linked': 198, 'to_review': 4, 'new_customer': 202}
returning customers correctly attached: 197/200, wrong attachments: 1
steward approved review item WEB-008319
GDPR erase C0000321: removed 6 source records
example golden record: C0000001 Gareth Smith ... n_source_records 3, sources BILLING,CRM,WEB, version 1
provenance: first_name/last_name/dob from CRM-005671 (most_frequent_then_source_priority), email/phone from BILLING-005670 (most_recent), ...
```

(Splink also prints a warning that `dob` and `postcode` m values were not fully trained; that is expected, defaults are used.)

How to read it:
- **4,144 customers for 8,192 records.** The data has 4,000 real people; the extra 144 customers are people split into more than one cluster by the batch matcher plus graph repair. The hub prefers a missed merge over a false one.
- **404 new records:** 198 attached automatically, 202 got a new customer id, and 4 of those 202 are in the review queue (the grey zone).
- **197/200, 1 wrong.** 200 new records belong to people already in the master; 197 were attached to the right customer. Of the 198 auto-links, 1 went to the wrong customer, so incremental precision is about 99.5%. The 3 returning people not attached are waiting as new customers or in review.
- **Golden record and provenance.** Names and DOB come from the CRM row (frequency then trust), contact fields from the most recently updated BILLING row. Every value can be explained.
- The `updated_at` timestamp in the example record changes with every run.

### Try this

1. Lower `AUTO_MATCH` to `0.80` (L62). More records auto-link and the review queue shrinks; watch `wrong attachments` for the precision cost (slide 13). Raise it to `0.99` and more correct matches fall to review or become new customers.
2. Delete or rename `results/clusters_graph.csv` and re-run. The hub seeds from `clusters_splink.csv`, which has more false merges (198 false-merge pairs versus 12 after repair), so golden records mix more people and `cust_truth` labels are noisier.
3. Change `SOURCE_PRIORITY` so `WEB` is `1`, or remove `"email"` from `RECENCY_FIELDS`, and compare the provenance block of `C0000001`: the winning source and `rule` for those fields change, the matching numbers do not (survivorship never changes membership).

---

## 06_customer_spine.py

**What it does.** Takes the mastered customers from the MDM hub (step 5) and publishes the customer spine: the thin, governed "Golden Layer" table that every downstream system joins to. It groups customers into households with an address graph, writes one parent-child identity hierarchy (HOUSEHOLD, CUSTOMER, SOURCE), and runs seven data contracts that must all pass before anything is exported. Generator truth is used only at the end, to measure how good the household grouping is.

**Run.** `python 06_customer_spine.py` (after `02_splink.py` and `05_mdm.py`, because it needs `results/splink_model.json` and `results/mdm.duckdb`).

**Reads / Writes.**
- Reads: `results/mdm.duckdb` (tables `golden_record`, `xref`, `source_record`), `results/splink_model.json` (only hashed), `data/customers.csv` and `data/new_batch.csv` (truth, evaluation only).
- Writes: new DuckDB tables `household`, `identity_hierarchy`, `customer_spine`, `column_classification` in `results/mdm.duckdb`; CSVs `results/customer_spine.csv`, `results/identity_hierarchy.csv`, `results/spine_contracts.csv`, `results/metrics_households.csv`.

**Slides.** 19 (Mini MDM, the input), 20 (Customer spine and hierarchy), 25 (Lakehouse mapping: the spine is the Gold layer), 14-15 (graph view, reused for households).

**Guide.** [3.8 MDM, golden record and customer spine](DEMO_GUIDE.md#38-mdm-golden-record-and-customer-spine), [3.7 Step 7. Hierarchies are graphs too](DEMO_GUIDE.md#step-7-hierarchies-are-graphs-too), [Code tour 6](DEMO_GUIDE.md#6-customer-spine-and-hierarchy-06_customer_spinepy), [FAQ: Spine, MDM and governance](DEMO_GUIDE.md#spine-mdm-and-governance).

**Walkthrough.**

1. [06_customer_spine.py#L1-L32](06_customer_spine.py#L1-L32) Module docstring. Defines the three hierarchy levels, the contracts, inputs, outputs and run order. Why it matters: the spine is a product with consumers, so its shape and guarantees are stated up front. Slide 20.
2. [06_customer_spine.py#L34-L53](06_customer_spine.py#L34-L53) Imports. `hashlib` fingerprints the model, `duckdb` is the MDM database, `networkx` finds connected components, `rapidfuzz` compares street strings, `evaluate_clusters` scores households against truth.
3. [06_customer_spine.py#L55-L73](06_customer_spine.py#L55-L73) Constants. `ADDRESS_SIMILARITY = 85` is the `fuzz.token_set_ratio` cut-off (0-100, word order and repeated words ignored) for "same street". `PII_COLUMNS` classifies every personal column of the spine (`PII`, `PII_SENSITIVE` for date of birth, `PII_LOW` for city and postcode). Why: governance metadata lives next to the code and a contract checks it. Slide 20.
4. [06_customer_spine.py#L76-L147](06_customer_spine.py#L76-L147) `households()`: households as a graph problem. Slides 14 and 20.
   - [L83-L88](06_customer_spine.py#L83-L88) An undirected graph whose nodes are customer ids (strings) and address nodes (tuples). Every customer is added first, so people with no address still form a one-person household.
   - [L89-L114](06_customer_spine.py#L89-L114) For each postcode, every source record's street is matched greedily against the representatives already seen in that postcode (first spelling that scores at least 85 wins, otherwise the street becomes a new representative). The customer is then joined to the node `("ADDR", postcode, street)`. Using all source records, not only the golden address, means a person whose survivorship picked a newer address still links to the home they once shared. Comparing only inside a postcode is a form of blocking: it limits false joins and work.
   - [L115-L147](06_customer_spine.py#L115-L147) Each connected component is a household. Address nodes are dropped to get the members. The rule is `single_person`, `same_address_same_surname` or `same_address`, and the household id reuses the digits of the smallest customer id (`C0000042` becomes `H0000042`), so the same members give the same id on every build.
5. [06_customer_spine.py#L150-L174](06_customer_spine.py#L150-L174) `build_hierarchy()`: one parent-child table for all levels. Households are roots, customers point to their household with the household rule, source records point to their customer with the MDM `match_method` and `match_probability` as the edge confidence. `valid_from` stamps the build. Why: every edge of the hierarchy is explainable (rule plus confidence). Slide 20.
6. [06_customer_spine.py#L177-L216](06_customer_spine.py#L177-L216) `contracts()`: seven SQL checks, each returning a violation count. One customer per source record, no source record missing from the crosswalk (anti-join), a golden record for every live customer, exactly one household per customer, the parent household exists, the spine key is unique, and all eight PII columns are classified. A contract passes only with zero violations. Why: governance is code that runs on every build, not a document. Slide 20.
7. [06_customer_spine.py#L219-L230](06_customer_spine.py#L219-L230) `main()` setup: open `results/mdm.duckdb`, take one UTC timestamp for the build, and compute the match model version as the first 12 hex characters of SHA-256 of `splink_model.json`. Why: lineage, so a consumer can tell which model produced each customer.
8. [06_customer_spine.py#L232-L243](06_customer_spine.py#L232-L243) Load `golden_record`, `xref`, and every source record's address with its customer, then build households and the hierarchy.
9. [06_customer_spine.py#L245-L250](06_customer_spine.py#L245-L250) `con.register()` exposes the pandas DataFrames to SQL, and `CREATE OR REPLACE TABLE` materialises `household` and `identity_hierarchy` (rebuilt each run).
10. [06_customer_spine.py#L251-L271](06_customer_spine.py#L251-L271) The `customer_spine` table: one row per golden customer with household, mastered attributes, `source_keys` (a DuckDB list such as `['CRM:CRM-000123', 'WEB:WEB-000456']`), `weakest_link_probability` (the least certain record, a steward signal), `golden_version`, `match_model_version` and `published_at`. `GROUP BY ALL` groups by every non-aggregated column. Slides 20 and 25.
11. [06_customer_spine.py#L272-L281](06_customer_spine.py#L272-L281) Write `column_classification` from `PII_COLUMNS` (in a lakehouse this would be catalog column tags).
12. [06_customer_spine.py#L283-L290](06_customer_spine.py#L283-L290) Run the contracts, print them, and stop with `SystemExit` (non-zero exit) if any fails, before anything is exported. Why: a broken spine never reaches consumers.
13. [06_customer_spine.py#L292-L311](06_customer_spine.py#L292-L311) Evaluation only. Truth from both CSVs is mapped onto each crosswalk row, then collapsed to one row per true person (the most common predicted household if the MDM split the person). `evaluate_clusters` gives pairwise precision and recall of "these two people live together". Truth is never used to build households.
14. [06_customer_spine.py#L312-L325](06_customer_spine.py#L312-L325) Print the summary: customers, multi-person households, household pair precision and recall, node counts per hierarchy level, and the model version.
15. [06_customer_spine.py#L327-L337](06_customer_spine.py#L327-L337) Publish: export the spine, hierarchy, contract results and household metrics as CSV (read by `09_compare.py`), then close the database.
16. [06_customer_spine.py#L340-L342](06_customer_spine.py#L340-L342) Standard script entry point.

**What you should see.**

```
                                       contract  violations  passed
   every source record has exactly one customer           0    True
     no source record without a crosswalk entry           0    True
        every live customer has a golden record           0    True
every customer belongs to exactly one household           0    True
              every customer's household exists           0    True
                            spine key is unique           0    True
                 every PII column is classified           0    True
customers: 4344, multi-person households: 177, people-in-household pair precision=0.9677 recall=0.7463
hierarchy nodes: {'SOURCE': 8586, 'CUSTOMER': 4344, 'HOUSEHOLD': 4164} | match model version: 4480632c71ba
```

How to read it: all seven contracts pass, so the spine is published. The spine has 4,344 customers (the 8,192 initial records plus the new batch, 8,586 source records in total, as mastered by step 5). 177 households have more than one person; the other households are single-person, giving 4,164 household nodes. When the script puts two people in one household it is right 97% of the time (precision 0.9677), and it finds 75% of true co-resident pairs (recall 0.7463). Misses are mostly people whose shared address never appears on their records (moves, web forms without an address). The model version hash changes whenever `splink_model.json` changes.

**Try this.**
- Lower `ADDRESS_SIMILARITY` ([L60](06_customer_spine.py#L60)) to 70: more street spellings collapse into one node, so recall rises and precision drops (neighbours on similar streets merge). Raise it to 95 and the opposite happens.
- Remove `"postcode"` from `PII_COLUMNS` ([L64-L73](06_customer_spine.py#L64-L73)): the contract "every PII column is classified" reports 1 violation and the script exits with "data contract failed: spine not published", and no CSV is rewritten.
- Build households from the golden address only (change the `members` query at [L237-L239](06_customer_spine.py#L237-L239) to read `address, postcode` from `golden_record`): recall falls, because people whose survivorship picked a newer address lose the link to the home they shared.

---

## 07_identity_drift.py

**What it does.** Runs the saved Splink model on two snapshots of the data: the initial records, and a later snapshot where 5% of records changed contact details and the new batch was added. Both are clustered from scratch. It then compares three ways of giving run-2 clusters a customer id (renumber every run, use a member record id, carry the run-1 id forward by overlap) and measures how many existing records got a different id.

**Run.** `python 07_identity_drift.py` (from `er-demo/`, after `02_splink.py`, which writes `results/splink_model.json`).

**Reads / Writes.**
- Reads `data/customers.csv`, `data/new_batch.csv`, `results/splink_model.json`; imports `MODEL_COLUMNS` from `02_splink.py`.
- Writes `results/identity_drift.csv` (drift rate per strategy), `results/id_alias.csv` (retired id to surviving id), `results/id_events.csv` (every new / split / merged_into event).

**Slides.** 21 (and the 56% to 0.2% headline on slide 3).

**Guide.** [3.10 Identity drift](DEMO_GUIDE.md#310-identity-drift); code tour [7. Identity drift](DEMO_GUIDE.md#7-identity-drift-07_identity_driftpy); FAQ [Drift, MLOps and feature stores](DEMO_GUIDE.md#drift-mlops-and-feature-stores).

### Walkthrough

1. [07_identity_drift.py#L1-L38](07_identity_drift.py#L1-L38) **Module docstring.** Defines identity drift, the two runs, the three id strategies and the drift rate, plus inputs, outputs and run order. Slide 21.
2. [07_identity_drift.py#L40-L56](07_identity_drift.py#L40-L56) **Imports.** `DuckDBAPI` and `Linker` from Splink score in an in-process DuckDB database. `02_splink.py` cannot be imported with a normal `import` because its name starts with a digit, so `__import__("02_splink")` loads it to reuse `MODEL_COLUMNS` (its `main()` does not run on import).
3. [07_identity_drift.py#L58-L63](07_identity_drift.py#L58-L63) **Constants.** `THRESHOLD = 0.95` matches 02, so run 1 reproduces its 4,102 customers. `UPDATE_RATE = 0.05` is the share of records whose contact details change.
4. [07_identity_drift.py#L66-L80](07_identity_drift.py#L66-L80) **`cluster()`.** Loads the trained model JSON into a new `Linker` (no retraining), scores candidate pairs at p >= 0.5, clusters at p >= 0.95 and returns Splink's `cluster_id` per `unique_id`. Keeping the model fixed means any drift comes from the data, not from a new model.
5. [07_identity_drift.py#L83-L89](07_identity_drift.py#L83-L89) **`sequential()`.** The naive approach: number clusters `C0000001...` in order of first appearance after sorting by record id. Any cluster that appears or disappears early in the order shifts every later number. Slide 21 (what not to do).
6. [07_identity_drift.py#L92-L128](07_identity_drift.py#L92-L128) **`carry_forward()`.** The remedy. It builds a table of record overlap between each run-2 cluster and each run-1 id ([L96-L98](07_identity_drift.py#L96-L98)), sorts by overlap size with ties broken by the lexically smaller (older) id ([L101](07_identity_drift.py#L101)), and greedily hands each old id to at most one new cluster ([L103-L107](07_identity_drift.py#L103-L107)). That is the split rule: the largest piece keeps the id. Clusters left without an id get a fresh number and an event: `split` if their records came from an old cluster, `new` if they are only new-batch records ([L109-L120](07_identity_drift.py#L109-L120)). Old ids that no cluster kept were merged; each gets a `merged_into` event pointing at the cluster that holds most of its records ([L122-L126](07_identity_drift.py#L122-L126)). Slide 21 (carry-forward rules).
7. [07_identity_drift.py#L131-L136](07_identity_drift.py#L131-L136) **`drift()`.** Share of records present in both runs whose id string differs. New-batch records cannot drift, so only the intersection counts.
8. [07_identity_drift.py#L139-L154](07_identity_drift.py#L139-L154) **`membership_changed()`.** The context number: share of run-1 records whose set of run-1 co-members is different in run 2. Labels are ignored and sets of records compared, so it measures real cluster change, which is close to the lower bound any id strategy can reach.
9. [07_identity_drift.py#L157-L176](07_identity_drift.py#L157-L176) **`main()`, building run 2.** With fixed seeds (7), 5% of records are picked; half get a new random `07...` mobile number, half lose their email. This weakens the evidence that held some clusters together. The new batch is appended.
10. [07_identity_drift.py#L178-L181](07_identity_drift.py#L178-L181) **Two clusterings.** Both snapshots are standardised and clustered from scratch with the same model.
11. [07_identity_drift.py#L183-L193](07_identity_drift.py#L183-L193) **The three strategies.** Run-1 ids are the sequential numbering (what was published). Run 2 gets a sequential numbering, a representative id (`R-` plus Splink's `cluster_id`, compared with the same form for run 1), and a carry-forward id whose fresh numbers start after the last run-1 number.
12. [07_identity_drift.py#L195-L207](07_identity_drift.py#L195-L207) **Report.** One row per strategy plus the context row, printed as a table, then the count of carry-forward events. Slides 21 and 3.
13. [07_identity_drift.py#L211-L216](07_identity_drift.py#L211-L216) **Outputs.** The drift table, the alias table (only merges, renamed to `retired_id` / `surviving_id` so old keys can be translated), and the full event log.
14. [07_identity_drift.py#L220-L221](07_identity_drift.py#L220-L221) Standard entry point.

### What you should see

Splink first prints its "untrained parameters" warning for `dob` and `postcode` twice, once per run (m values not fully trained); that is expected with the saved model. Then:

```text
run 1: 4102 customers, run 2: 4309 customers
                              strategy  drift_rate
                            sequential      0.5613
                        representative      0.0087
                         carry_forward      0.0020
context: records whose cluster changed      0.0051
carry-forward events: {'new': 201, 'split': 11, 'merged_into': 5}
```

How to read it:
- Run 1 gives the same 4,102 customers as `02_splink.py`; run 2 has 4,309, about 200 more from the new batch plus a few splits.
- Sequential renumbering changes 56% of existing ids although only 0.51% of records really changed cluster. That is pure drift.
- The representative id changes 0.87%: when a cluster changes, its representative record can change, and every member then gets a new id.
- Carry-forward changes only 0.20%, below the 0.51% context figure: only the records that split off or merged in move, everyone else in a changed cluster keeps their id.
- Events: 201 brand-new customers, 11 split-off pieces with new ids, 5 retired ids recorded in `id_alias.csv`.

### Try this

1. Set `UPDATE_RATE = 0.2` (line 63). More records lose evidence, so more clusters split: the context figure, the number of `split` events and every drift rate rise, but carry-forward stays far below sequential.
2. Change `THRESHOLD` to 0.99 (line 61). Clusters get smaller and more fragile, so small data changes split them more often; watch `split` and `merged_into` counts.
3. Open `results/id_alias.csv` and compare the ids. In this run one of the five merges keeps the higher (younger) id, `C0000208` retired into `C0002630`, because the surviving piece is chosen by largest overlap first and age only breaks ties (line 101).

---

## 08_mlops_feature_store.py

**What it does.** Runs the supervised matcher from step 3 as a product. Pair features go into a small versioned feature store in DuckDB, two model versions are trained on a strict entity-disjoint split, registered with their metrics, and passed through a promotion gate that moves the `champion` alias. The champion then scores a normal incoming batch and a deliberately broken feed, and label-free KPIs with PSI drift alerts show which one is healthy.

**Run.** `python 08_mlops_feature_store.py` (needs only `data/customers.csv` and `data/new_batch.csv` from `data/generate_data.py`; it reuses blocking from `01_rules_rapidfuzz.py` and features from `03_ml_recordlinkage.py`). MLflow logging happens only if `mlflow` is installed.

**Reads / Writes.**
- Reads: `data/customers.csv`, `data/new_batch.csv`.
- Writes: `results/feature_store.duckdb` (tables `feature_definitions`, `pair_features_train`, `pair_features_new_batch`, `pair_features_broken_feed`), `results/model_registry/matcher_v1.pkl`, `matcher_v2.pkl`, `registry.json`, `results/model_versions.csv`, `results/monitoring_report.csv`, and `results/mlruns/` if MLflow is installed. The registry and feature store are deleted at the start of each run.

**Slides.** 22 (Section MLOps), 23 (Feature store, registry, gate), 24 (Monitoring), 11 (Supervised features), 13 (Precision or recall), 25 (Lakehouse mapping), 27 (Results chart).

**Guide.** [3.11 MLOps and feature stores](DEMO_GUIDE.md#311-mlops-and-feature-stores), [3.6 Step 5. Evaluate without fooling yourself](DEMO_GUIDE.md#step-5-evaluate-without-fooling-yourself), [3.6 Step 6. Confidence: is p = 0.9 really 90%?](DEMO_GUIDE.md#step-6-confidence-is-p--09-really-90), [3.9 Matching-quality metrics](DEMO_GUIDE.md#39-matching-quality-metrics), [Code tour 8](DEMO_GUIDE.md#8-mlops-and-feature-store-08_mlops_feature_storepy), [FAQ: Drift, MLOps and feature stores](DEMO_GUIDE.md#drift-mlops-and-feature-stores).

**Walkthrough.**

1. [08_mlops_feature_store.py#L1-L38](08_mlops_feature_store.py#L1-L38) Module docstring: the four parts (feature store, evaluation, registry, monitoring), inputs, outputs, run order. Slide 23.
2. [08_mlops_feature_store.py#L40-L77](08_mlops_feature_store.py#L40-L77) Imports. Two model families (logistic regression in a pipeline, `HistGradientBoostingClassifier`), `average_precision_score` (area under the precision-recall curve) and `brier_score_loss` (mean squared error of probabilities). Steps 1 and 3 are loaded with `__import__` because their file names start with a digit; reusing them keeps blocking and features identical to the earlier steps.
3. [08_mlops_feature_store.py#L79-L89](08_mlops_feature_store.py#L79-L89) Constants and `now()`. `THRESHOLD = 0.9` is the match decision (same as step 3). `PSI_ALERT = 0.2` follows the usual rule of thumb (below 0.1 stable, 0.1 to 0.2 watch, above 0.2 act). Slide 24.
4. [08_mlops_feature_store.py#L93-L163](08_mlops_feature_store.py#L93-L163) `FeatureStore`, a tiny offline feature store. Slide 23.
   - [L96-L103](08_mlops_feature_store.py#L96-L103) Opens the DuckDB file and creates the `feature_definitions` catalogue.
   - [L105-L115](08_mlops_feature_store.py#L105-L115) `version()`: SHA-256 of the sorted feature names plus the fitted TF-IDF vocabulary, shortened to `fs_` plus 10 hex characters. Refitting TF-IDF on other data changes the vocabulary and therefore the version.
   - [L117-L137](08_mlops_feature_store.py#L117-L137) `register()`: writes one catalogue row per feature, only once per version (idempotent).
   - [L139-L150](08_mlops_feature_store.py#L139-L150) `write()`: turns the pair MultiIndex into `id_l`, `id_r` columns, stamps `feature_set_version` and `computed_at`, and replaces the table.
   - [L152-L163](08_mlops_feature_store.py#L152-L163) `read()`: refuses a table whose version differs from the one the model expects (`ValueError`). Why: this is the guard against training/serving skew.
5. [08_mlops_feature_store.py#L167-L183](08_mlops_feature_store.py#L167-L183) `ece()`: expected calibration error. Probabilities go into 10 equal-width bins; each bin's gap between observed match rate and mean predicted p is weighted by its share of pairs. Low ECE means "p = 0.9" really is right about 90% of the time, which matters because steps 2 and 5 route pairs by probability. Slide 23.
6. [08_mlops_feature_store.py#L186-L208](08_mlops_feature_store.py#L186-L208) `psi()`: population stability index, the sum of `(actual% - expected%) * ln(actual% / expected%)` over buckets. Bucket edges are the reference deciles (duplicates removed for binary features), missing values get their own bucket so a jump in nulls is visible, and empty buckets are clipped to 0.0001 to avoid log of zero. Slide 24.
7. [08_mlops_feature_store.py#L211-L231](08_mlops_feature_store.py#L211-L231) `evaluate()`: scores the test pairs, keeps pairs with p of at least 0.9, clusters them with union-find, and reports pair metrics (average precision, Brier, ECE) and cluster metrics (B-cubed F1, pair precision and recall, largest cluster as a chaining detector). Why: the customer table experiences clusters, not pairs. Slides 13 and 15.
8. [08_mlops_feature_store.py#L235-L266](08_mlops_feature_store.py#L235-L266) The registry: `load_registry()` and `save_registry()` read and write `registry.json` (`versions` list plus `aliases` map), `register()` pickles the model as `matcher_v{n}.pkl` and stores its model type, feature-set version, threshold, metrics and timestamp. Slide 23.
9. [08_mlops_feature_store.py#L269-L287](08_mlops_feature_store.py#L269-L287) `promotion_gate()`: three checks in order. ECE must be at most 0.05; the first acceptable model becomes champion; afterwards B-cubed F1 must be at least the champion's and the largest cluster must not grow by more than 2 (no new chaining). Slide 23.
10. [08_mlops_feature_store.py#L290-L307](08_mlops_feature_store.py#L290-L307) `log_to_mlflow()`: optional mirror of each registry entry to a local MLflow store (params, metrics, `promoted` tag, pickle artifact). Silently skipped without MLflow.
11. [08_mlops_feature_store.py#L311-L326](08_mlops_feature_store.py#L311-L326) `batch_pairs()`: blocks old and new records together with the step 1 keys, keeps only pairs with exactly one new record, and puts the old id on the left. Slide 7.
12. [08_mlops_feature_store.py#L329-L348](08_mlops_feature_store.py#L329-L348) `monitor()`: label-free KPIs for a scored batch: candidate pairs, match rate (p of at least 0.9), grey-zone share (0.5 to 0.9, the review load), PSI of the score against the training scores, and PSI of every feature, each flagged when above 0.2. Slide 24.
13. [08_mlops_feature_store.py#L353-L359](08_mlops_feature_store.py#L353-L359) `main()` starts with a fresh registry and feature store file so the demo is repeatable.
14. [08_mlops_feature_store.py#L361-L378](08_mlops_feature_store.py#L361-L378) Load and standardise the training snapshot, block it (6,405 pairs), fit TF-IDF once, compute the 14 pair features with step 3's `features()`, version them, register the definitions and write `pair_features_train`. Slides 7, 11, 23.
15. [08_mlops_feature_store.py#L380-L384](08_mlops_feature_store.py#L380-L384) Training reads the features back from the store, as a scheduled job would, and builds labels: 1 when both records share a true person id.
16. [08_mlops_feature_store.py#L386-L398](08_mlops_feature_store.py#L386-L398) Strict entity-disjoint split: a third of the people (seed 0) are test people. Train pairs have both records from train people, test pairs both from test people; cross-boundary pairs are dropped. Why: a random pair split leaks the same person into train and test and inflates the metrics. Slide 12.
17. [08_mlops_feature_store.py#L400-L425](08_mlops_feature_store.py#L400-L425) Train, evaluate, register and gate each candidate in order (v1 logistic regression with imputation and scaling, v2 gradient boosting). Promotion moves only the alias; old versions stay in the registry. Slide 23.
18. [08_mlops_feature_store.py#L427-L431](08_mlops_feature_store.py#L427-L431) Serving loads the champion by alias from the registry file and computes the reference score distribution on the training pairs.
19. [08_mlops_feature_store.py#L433-L439](08_mlops_feature_store.py#L433-L439) Two batches: the real `new_batch.csv` and a broken feed where phones are missing and first names are reduced to initials. Slide 24.
20. [08_mlops_feature_store.py#L440-L457](08_mlops_feature_store.py#L440-L457) For each batch: standardise, block against the existing records, compute features with the training vectorizer, write them through the store and read them back with the champion's feature-set version (the skew check), run `monitor()`, and print the four headline KPIs and any alerts.
21. [08_mlops_feature_store.py#L458-L464](08_mlops_feature_store.py#L458-L464) Export `monitoring_report.csv` (long format: batch, kpi, value, alert) and `model_versions.csv` (one row per version), both read by `09_compare.py`.
22. [08_mlops_feature_store.py#L467-L469](08_mlops_feature_store.py#L467-L469) Standard script entry point.

**What you should see.**

```
feature store: 6405 pair rows, 14 features, version fs_dc5909e646
entity-disjoint split: 4197 train pairs, 1857 test pairs
v1 logistic_regression: {'average_precision': 0.9999, 'brier': 0.0093, 'ece': 0.0122, 'bcubed_f1': 0.9874, 'pair_precision': 1.0, 'pair_recall': 0.9538, 'largest_cluster': 5} -> PROMOTED (no champion yet)
v2 gradient_boosting: {'average_precision': 1.0, 'brier': 0.0032, 'ece': 0.0038, 'bcubed_f1': 0.993, 'pair_precision': 0.9935, 'pair_recall': 0.9777, 'largest_cluster': 5} -> PROMOTED (B-cubed F1 0.993 >= champion 0.9874)
monitoring new_batch: {'candidate_pairs': 439, 'match_rate': 0.8929, 'grey_zone_share': 0.0, 'psi_score': 0.027} alerts: none
monitoring broken_feed: {'candidate_pairs': 303, 'match_rate': 0.9835, 'grey_zone_share': 0.0066, 'psi_score': 2.7695} alerts: ['psi_score', 'psi_first_jw', 'psi_phone_exact', 'psi_record_tfidf_cos']
```

How to read it:
- The feature store holds the same 6,405 blocked pairs as steps 1 to 3, with 14 features. The version hash stays the same as long as features and data do not change.
- The split keeps 4,197 + 1,857 = 6,054 pairs; the other 351 pairs cross the train/test boundary and are dropped.
- v1 is promoted because there is no champion yet. v2 has better ranking, Brier and calibration (ECE 0.004 against 0.012) and higher B-cubed F1 (0.993 against 0.987) with no extra chaining (largest cluster 5 for both), so it becomes champion. Note v1's pair precision 1.0 with lower recall: the linear model is more cautious.
- The normal batch has score PSI 0.027 (stable) and no alerts. The broken feed has score PSI 2.77 and alerts on the score, `first_jw`, `phone_exact` and `record_tfidf_cos`, which point straight at the broken inputs. Its match rate looks better (0.98 against 0.89) only because about a third of candidate pairs vanished (phone was a blocking key). One KPI alone would hide the incident.

**Try this.**
- Tighten the calibration gate: change `0.05` to `0.01` in [L275](08_mlops_feature_store.py#L275). v1 (ECE 0.0122) is now rejected with "calibration too poor", so v2 is promoted as "no champion yet".
- Swap the order of `candidates` ([L402-L409](08_mlops_feature_store.py#L402-L409)) so gradient boosting is v1. Logistic regression then fails the gate (B-cubed F1 0.9874 below 0.993) and is "kept as challenger".
- Make the broken feed milder, for example drop only the `phone=None` line ([L437](08_mlops_feature_store.py#L437)). Expect fewer alerts (mainly `psi_phone_exact` and the score), showing that per-feature PSI tells you which source broke.

---

## 09_compare.py

**What it does:** the report step. It reads the metric CSVs that steps 1 to 8 left in `results/`, renders them as Markdown tables and writes one file, `results/comparison.md`. It computes nothing new, so it is fast and safe to rerun; any input that is missing is skipped, so a partial pipeline still yields a partial report (at least one matcher file must exist).

**Run:** `python 09_compare.py` (last line of [run_all.sh](run_all.sh)).

**Reads / Writes:** reads `results/metrics_rapidfuzz.csv`, `metrics_splink.csv`, `metrics_ml.csv`, `metrics_graph.csv`, and optionally `metrics_households.csv`, `spine_contracts.csv`, `identity_drift.csv`, `model_versions.csv`, `monitoring_report.csv`. Writes `results/comparison.md` and prints the same text.

**Slides:** 27 (Results chart: the matcher table), 28 (Lessons), plus the tables behind 20 (spine contracts, households), 21 (drift), 23 and 24 (registry and monitoring).

**Guide:** [9. Report](DEMO_GUIDE.md#9-report-09_comparepy), [5. Ten-minute walkthrough](DEMO_GUIDE.md#5-ten-minute-walkthrough), [1. Run the demo](DEMO_GUIDE.md#1-run-the-demo) (keep `comparison.md` open in a tab).

**Walkthrough**

1. [09_compare.py#L1-L12](09_compare.py#L1-L12) Docstring: inputs, output, how to run, slides.
2. [09_compare.py#L14-L19](09_compare.py#L14-L19) Imports and `RES`, the `results/` folder next to the script.
3. [09_compare.py#L20-L30](09_compare.py#L20-L30) The four matcher metric files (rules, Splink, ML, and the two graph repair rows), stacked with `pd.concat` for those that exist. One row per method gives the like-for-like comparison of slide 27.
4. [09_compare.py#L31-L43](09_compare.py#L31-L43) `cols`: the columns shown. They include `false_merges_pairs`, `missed_pairs` and `largest_cluster`, not just precision and recall, because the story of the demo is about error counts and chaining (slide 13, 15).
5. [09_compare.py#L44-L49](09_compare.py#L44-L49) Start the report: heading plus the matcher table via `DataFrame.to_markdown()` (which needs the `tabulate` package).
6. [09_compare.py#L50-L62](09_compare.py#L50-L62) Optional sections from steps 6 to 8: households (only five columns kept), spine data contracts, identity drift and the model registry, each appended only if its CSV exists.
7. [09_compare.py#L63-L76](09_compare.py#L63-L76) Monitoring: the CSV is in long format (batch, kpi, value, alert), so the four headline KPIs are pivoted into one row per KPI and one column per batch, followed by a line listing every PSI check that crossed the 0.2 alert threshold (slide 24).
8. [09_compare.py#L77-L80](09_compare.py#L77-L80) Join the blocks, write `results/comparison.md` and print it.

**What you should see:** the matcher table (seed 42):

| method | pair P | pair R | B3-F1 | entities | largest | false merges | missed |
|:--|--:|--:|--:|--:|--:|--:|--:|
| rules + rapidfuzz | 0.9523 | 0.9127 | 0.9707 | 4278 | 9 | 267 | 510 |
| splink (EM, p>=0.95) | 0.9661 | 0.9649 | 0.9853 | 4102 | 7 | 198 | 205 |
| recordlinkage + gradient boosting (p>=0.9) | 0.9757 | 0.9752 | 0.9898 | 4082 | 7 | 142 | 145 |
| splink + graph repair | 0.9979 | 0.9617 | 0.9889 | 4144 | 6 | 12 | 224 |
| ml + graph repair | 0.9984 | 0.9723 | 0.9918 | 4108 | 6 | 9 | 162 |

How to read it: each matcher is better than the last, but the big jump in precision comes from the graph step, which cuts false merges from 198 to 12 (Splink) and 142 to 9 (ML) for a small loss of recall. The later sections show households (pair precision 0.9677, recall 0.7463), all seven spine contracts passing with 0 violations, drift rates 0.5613 (sequential), 0.0087 (representative), 0.0020 (carry forward), the registry (v1 logistic regression ECE 0.0122, v2 gradient boosting ECE 0.0038, B-cubed F1 0.993) and monitoring (new batch PSI 0.027, no alerts; broken feed PSI 2.7695 with alerts on `psi_score`, `psi_first_jw`, `psi_phone_exact`, `psi_record_tfidf_cos`).

**Try this**

1. Delete `results/identity_drift.csv` and rerun `09_compare.py`: the drift section disappears and the rest of the report is unchanged, showing the skip-if-missing logic on [L58-L62](09_compare.py#L58-L62).
2. Add `"bcubed_precision"` and `"bcubed_recall"` to `cols`: the table shows that B-cubed precision stays high even for the rules matcher, because most of its errors are in a few clusters.
3. Rerun only `02_splink.py` with a different threshold, then `09_compare.py`: only the Splink row moves, because the report just reads whatever each step last wrote (the "splink + graph repair" row changes only after you also rerun `04_graph_resolution.py`).

---

## run_all.sh

**What it does:** runs the whole demo end to end in pipeline order (slide 4): generate data, three matchers, graph repair, MDM, customer spine, identity drift, MLOps, then the report. It stops at the first failing step (`set -e`), so a later step never runs on stale or missing inputs. Each step reads the files the previous ones wrote, so the order is part of the design, not a convenience.

**Run:** `./run_all.sh` (or `bash run_all.sh`) from anywhere; it changes into its own folder first. To choose an interpreter: `PYTHON=.venv/bin/python ./run_all.sh`. On Windows PowerShell use the explicit sequence in [1. Run the demo](DEMO_GUIDE.md#1-run-the-demo). A full run takes about 45 seconds on a laptop.

**Reads / Writes:** everything the steps read and write: `data/customers.csv`, `data/new_batch.csv`, and the `results/` folder (metric CSVs, clusters, `mdm.duckdb`, `feature_store.duckdb`, `model_registry/`, Splink charts, and finally `comparison.md`).

**Slides:** 4 (Pipeline), 29 (Get the code). Each line's comment names the slides for that step.

**Guide:** [1. Run the demo](DEMO_GUIDE.md#1-run-the-demo), [End-to-end flow](DEMO_GUIDE.md#end-to-end-flow), [10. Troubleshooting](DEMO_GUIDE.md#10-troubleshooting).

**Walkthrough**

1. [run_all.sh#L1-L5](run_all.sh#L1-L5) Shebang (`bash` via `env`, so it works wherever bash is on the PATH) and a usage header.
2. [run_all.sh#L7-L8](run_all.sh#L7-L8) `set -e`: abort on the first non-zero exit code.
3. [run_all.sh#L9-L10](run_all.sh#L9-L10) `cd "$(dirname "$0")"`: run from the script's folder so relative paths like `data/` and `results/` resolve, whatever the caller's current directory.
4. [run_all.sh#L11-L13](run_all.sh#L11-L13) `${PYTHON:-python3}` uses `$PYTHON` if set, otherwise `python3`. Step 0 creates the known-truth data (slide 5).
5. [run_all.sh#L14-L19](run_all.sh#L14-L19) The three matchers: hand-built rules with rapidfuzz (slides 7, 8), Splink Fellegi-Sunter with EM (slides 9, 10), supervised gradient boosting on recordlinkage features (slides 11 to 13).
6. [run_all.sh#L20-L21](run_all.sh#L20-L21) Graph repair with cannot-link constraints and minimum cut (slides 15 to 17). Needs the Splink and ML pair scores from steps 2 and 3.
7. [run_all.sh#L22-L25](run_all.sh#L22-L25) Mastering: mini MDM with golden records and the incremental batch (slide 19), then customer spine, households and hierarchy (slide 20).
8. [run_all.sh#L26-L29](run_all.sh#L26-L29) Identity drift across two runs (slide 21) and the feature store, registry, promotion gate and monitoring (slides 23, 24). `05_mdm.py` and `08_mlops_feature_store.py` reset their databases, so reruns start from the same state.
9. [run_all.sh#L30-L31](run_all.sh#L30-L31) Collect everything into `results/comparison.md` (slide 27).

**What you should see:** the first lines are

```text
customers.csv: 8192 records for 4000 people
new_batch.csv: 400 records
households with 2 people: 183
blocking: {'candidate_pairs': 6405, 'pair_completeness': 0.9649, 'reduction_ratio': 0.999809}
```

followed by each step's summary: rules 267 false merges / 510 missed; Splink 198 / 205 and `review queue (0.5 <= p < 0.95): 161 pairs`; ML 142 / 145; graph repair 12 (Splink: 42 components split, 80 edges cut) and 9 (ML); MDM `incremental batch: {'auto_linked': 198, 'to_review': 4, 'new_customer': 202}` and `returning customers correctly attached: 197/200`; spine `customers: 4344, multi-person households: 177`; drift 0.5613 / 0.0087 / 0.0020; MLOps v1 then v2 promoted, broken-feed PSI 2.7695 with four alerts; and finally the `comparison.md` tables. Splink prints several `WARNING` blocks about levels "not observed in dataset" and untrained `m` values for `dob` and `postcode`; they are expected (some comparison levels never occur in this synthetic data) and do not stop the run.

**Try this**

1. Run `PYTHON=.venv/bin/python ./run_all.sh` to use the project virtual environment without activating it.
2. Comment out the `04_graph_resolution.py` line and rerun: `09_compare.py` still produces a report, but the graph rows come from the previous run's `metrics_graph.csv` (or are missing on a clean checkout), which shows why the whole sequence should be run together. On a clean checkout `05_mdm.py` then falls back to `clusters_splink.csv`, so the MDM starts from unrepaired clusters.
3. Time it with `time ./run_all.sh` and compare with the roughly 45 seconds quoted in the guide; then time single steps to see which dominate.

---

## databricks/splink_on_databricks.py

> **Not run locally.** This is a Databricks notebook (exported as source). It needs a Databricks workspace, the `spark` session Databricks provides, a Unity Catalog Silver table `customer_std` and a checkpoint volume. It is a design example and is not part of the verified laptop pipeline or `run_all.sh`; no numbers below come from running it.

**What it does.** Runs the same Fellegi-Sunter model as `02_splink.py` (same blocking rules, comparisons and training steps) on Spark through Splink's `SparkAPI` instead of `DuckDBAPI`. Pairs, clusters and the steward review queue are written as Delta tables in Unity Catalog, and the model JSON, parameters and label-free KPIs are logged to one MLflow run. It shows how each local file maps to a lakehouse layer.

**Run.** Import the file into a Databricks workspace (it opens as a notebook with Markdown and code cells), attach a cluster with Spark 3.4+ and `%pip install splink`, then run all cells. Locally you can only check that it compiles: `python -m py_compile databricks/splink_on_databricks.py`.

**Reads / Writes.**
- Reads the Unity Catalog table `main.customer_mdm.customer_std` (one standardised row per source record, the columns `common/standardise.py` creates).
- Writes Delta tables `pairs`, `clusters`, `review_queue` in `main.customer_mdm`; checkpoints in `/Volumes/main/customer_mdm/checkpoints`; `/tmp/splink_model.json` logged as an MLflow artifact, plus MLflow params and metrics.

**Slides.** 25 (lakehouse mapping), 26 (framework at scale), 23 (MLflow, champion alias).

**Guide.** Code tour [Optional integrations](DEMO_GUIDE.md#optional-integrations-databrickssplink_on_databrickspy-and-zinggzingg_customerspy); [7. System design: the framework at scale](DEMO_GUIDE.md#7-system-design-the-framework-at-scale); [3.5 Fellegi-Sunter](DEMO_GUIDE.md#35-fellegi-sunter-step-by-step) and [Step 8. How the model learns m and u](DEMO_GUIDE.md#step-8-how-the-model-learns-m-and-u-without-labels) for the training calls; [3.11 MLOps and feature stores](DEMO_GUIDE.md#311-mlops-and-feature-stores).

### Walkthrough

1. [databricks/splink_on_databricks.py#L1-L17](databricks/splink_on_databricks.py#L1-L17) **Markdown cell.** `# Databricks notebook source` marks the file as a notebook; `# MAGIC %md` lines render as Markdown. The table maps local pieces to Databricks: CSVs to Bronze Delta tables, `common/standardise.py` to the Silver table, `DuckDBAPI` to `SparkAPI`, `results/*.csv` to Unity Catalog tables, `splink_model.json` to an MLflow artifact with a `champion` alias. Slide 25.
2. [databricks/splink_on_databricks.py#L19-L48](databricks/splink_on_databricks.py#L19-L48) **Cell separator and docstring.** `# COMMAND ----------` starts a new cell. The docstring states inputs, outputs, how to run, and that the file is not executed in the demo.
3. [databricks/splink_on_databricks.py#L50-L56](databricks/splink_on_databricks.py#L50-L56) **Imports.** `mlflow` for run tracking, Splink's comparison library, Spark column functions `F`, and `SparkAPI` as the backend.
4. [databricks/splink_on_databricks.py#L58-L67](databricks/splink_on_databricks.py#L58-L67) **Workspace setup.** Sets the default catalog and schema, sets a checkpoint directory on a Unity Catalog volume (Splink's iterative Spark jobs build long query plans that checkpoints cut), and loads the Silver table. `spark` is a global Databricks provides, hence the `noqa: F821`.
5. [databricks/splink_on_databricks.py#L70-L92](databricks/splink_on_databricks.py#L70-L92) **Settings.** Identical to `02_splink.py`: dedupe within one combined table, five blocking rules (email, phone, DOB + surname metaphone, postcode + first-name metaphone, canonical first name + last name) and seven comparisons with term-frequency adjustment on names. Only the local `retain_intermediate_calculation_columns=True` is absent. Slide 7 (blocking) and slide 9 (fields and levels) explain the content.
6. [databricks/splink_on_databricks.py#L96-L98](databricks/splink_on_databricks.py#L96-L98) **Backend and linker.** `break_lineage_method="delta_lake_table"` makes Splink materialise intermediate results as Delta tables. The linker is built exactly as locally, just on the Spark DataFrame.
7. [databricks/splink_on_databricks.py#L102-L114](databricks/splink_on_databricks.py#L102-L114) **Training inside an MLflow run.** The prior from deterministic rules with assumed recall 0.7, `estimate_u_using_random_sampling` (u = how often different people agree by chance, from random pairs; 5e7 pairs here against 2e6 locally, because Spark can afford more), then expectation maximisation for m on three blocks so every field is learned at least once. No labels are used. Slide 9.
8. [databricks/splink_on_databricks.py#L118-L128](databricks/splink_on_databricks.py#L118-L128) **Predict, cluster, save.** Scores pairs at p >= 0.2, clusters at p >= 0.95, writes `pairs` and `clusters` as Delta tables and the grey zone 0.5 <= p < 0.95 as `review_queue` for stewards. Same thresholds as the local run. Slide 13 (two thresholds).
9. [databricks/splink_on_databricks.py#L132-L134](databricks/splink_on_databricks.py#L132-L134) **Model lineage.** Saves the trained model JSON and logs it plus the thresholds to MLflow, so every table can be traced to the exact model. Slide 23.
10. [databricks/splink_on_databricks.py#L136-L146](databricks/splink_on_databricks.py#L136-L146) **Label-free KPIs.** Number of records, number of entities, largest cluster and review-queue size, logged every run. A jump in `max_cluster_size` is the chaining alarm. With a steward golden set you would also log precision and recall with `common/evaluate.py` and compare to the champion. Slide 24.
11. [databricks/splink_on_databricks.py#L148-L155](databricks/splink_on_databricks.py#L148-L155) **Next tasks (Markdown).** Golden record and xref in Spark SQL, incremental matching from Change Data Feed, a steward app, PII column masks, optional vector-search blocking. Slides 25 and 26.

### What you should see

Nothing locally: the notebook is not executed in this demo. In a workspace you would expect the three Delta tables, and one MLflow run named `splink_customer_matching` with the model artifact, `cluster_threshold` and `review_band` params, and the four KPIs. On the same synthetic data they should be close to the local Splink run (8,192 records, about 4,102 entities, largest cluster 7, review queue about 161 pairs), but Spark sampling for u and EM can make small differences.

### Try this

1. Change the review band in the filter (line 127) to 0.8 to 0.95 and compare `review_queue_size` in MLflow: a smaller queue for stewards, more missed matches left unreviewed.
2. Lower `max_pairs` (line 110) to 2e6, the local value, and compare the logged `n_entities` across two runs to see how stable u estimation is.
3. Note that `linker.inference.predict_between(...)` in the Markdown (line 152) is a placeholder name; check the Splink docs of your version for the incremental API (for example `find_matches_to_new_records`) before building that task.

---

## zingg/zingg_customers.py

> **Not run locally.** Zingg needs Spark 3.5 and the Zingg jar (the `zingg/zingg` Docker image or a Databricks install), plus a human labelling session. It is not part of `run_all.sh`, and no numbers in the demo come from it. Check the field and match-type names against the Zingg version you install.

**What it does.** Configures Zingg, an open-source ML entity-resolution tool on Spark that learns from a small set of human labels (active learning). The script describes the input columns and how each may be compared, points Zingg at `data/customers.csv`, and runs one Zingg phase chosen on the command line: find uncertain pairs, label them, train, or match.

**Run.** In Docker, from `er-demo/`:

```bash
docker run -it -v $PWD:/demo zingg/zingg:0.4.0 bash
./scripts/zingg.sh --run /demo/zingg/zingg_customers.py findTrainingData
./scripts/zingg.sh --run /demo/zingg/zingg_customers.py label
# repeat findTrainingData + label until about 30-40 positive pairs
./scripts/zingg.sh --run /demo/zingg/zingg_customers.py train
./scripts/zingg.sh --run /demo/zingg/zingg_customers.py match
```

Locally you can only check that it compiles: `python -m py_compile zingg/zingg_customers.py`.

**Reads / Writes.**
- Reads `/demo/data/customers.csv` (the raw records; Zingg does its own normalisation, `common/standardise.py` is not used).
- Writes `/demo/zingg/models/customers_v1/` (labelled pairs, learned blocking and classifier) and `/demo/results/zingg_output/` (match output with `z_cluster`, `z_minScore`, `z_maxScore` per record).

**Slides.** 8 (licence note: Zingg Community is AGPL-3.0), 12 (where labels come from: human review).

**Guide.** Code tour [Optional integrations](DEMO_GUIDE.md#optional-integrations-databrickssplink_on_databrickspy-and-zinggzingg_customerspy); [3.6 Supervised matching](DEMO_GUIDE.md#36-supervised-matching-step-by-step), in particular [Step 7. Where it fails, and where labels come from](DEMO_GUIDE.md#step-7-where-it-fails-and-where-labels-come-from).

### Walkthrough

1. [zingg/zingg_customers.py#L1-L32](zingg/zingg_customers.py#L1-L32) **Module docstring.** The Zingg workflow in six steps (findTrainingData, label, repeat, train, match, link / runIncremental), inputs, outputs, the Docker commands and the licence note. Slides 8 and 12.
2. [zingg/zingg_customers.py#L33-L39](zingg/zingg_customers.py#L33-L39) **Imports.** `Arguments` holds the job configuration, `FieldDefinition` and `MatchType` describe columns, `Zingg` and `ClientOptions` run a phase, `CsvPipe` is a CSV source or sink.
3. [zingg/zingg_customers.py#L42-L44](zingg/zingg_customers.py#L42-L44) **Phase and base path.** The phase comes from the first command-line argument (default `findTrainingData`); `/demo` is where the Docker command mounts `er-demo/`.
4. [zingg/zingg_customers.py#L50-L64](zingg/zingg_customers.py#L50-L64) **Field definitions.** One entry per CSV column. Names, address and city are `FUZZY`; DOB and phone `EXACT`; email `EMAIL` (compares the part before the @); postcode `PINCODE`. Ids, source system, timestamps and the synthetic `true_entity_id` are `DONT_USE`: carried to the output for evaluation, never used to match. This is the Zingg counterpart of Splink's comparisons. Slide 8.
5. [zingg/zingg_customers.py#L67-L76](zingg/zingg_customers.py#L67-L76) **Job arguments.** The model id `customers_v1` ties all phases to one model folder; 4 Spark partitions; `setLabelDataSampleSize(0.4)` samples 40% of the data when looking for uncertain pairs to show the labeller.
6. [zingg/zingg_customers.py#L79-L87](zingg/zingg_customers.py#L79-L87) **Input and output pipes.** The Spark schema string lists the CSV columns as strings; the input pipe reads `customers.csv` with a header; the output pipe receives the match results. Note that the schema lists 12 columns while the CSV also has a 13th, `true_household_id`; Spark ignores the extra trailing column, but add it if you want it in the output.
7. [zingg/zingg_customers.py#L90](zingg/zingg_customers.py#L90) **Run the phase.** Builds the Zingg client for the chosen phase and executes it on Spark.
8. [zingg/zingg_customers.py#L92-L94](zingg/zingg_customers.py#L92-L94) **Evaluation hint.** After `match`, load the output and score it with the shared `evaluate_clusters()` so Zingg can join the comparison table in `results/comparison.md`.

### What you should see

Nothing locally: the script is not executed in this demo. In Docker, `findTrainingData` and `label` show you pairs to mark as match / no match / not sure; after `train` and `match`, `results/zingg_output/` holds one row per record with `z_cluster` (the resolved customer) and `z_minScore` / `z_maxScore` (the lowest and highest match score between that record and the others in its cluster). There are no reference numbers; evaluate with `evaluate_clusters(out.source_record_id, out.z_cluster, out.true_entity_id)` and compare with the Splink and ML rows (pair precision 0.966 and 0.976).

### Try this

1. Label more rounds before `train` (40 to 80 positive pairs instead of 30) and compare B-cubed F1: active learning usually improves quickly with the first labels and then flattens.
2. Change `dob` from `MatchType.EXACT` to `MatchType.FUZZY` (line 55) so day/month swaps and typos still count as partial agreement; expect higher recall and some extra false merges.
3. Set `postcode` to `MatchType.DONT_USE` (line 60) to see how much the model relies on location evidence.

