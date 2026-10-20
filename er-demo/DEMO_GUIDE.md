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

### 3.5 Fellegi-Sunter, step by step

Fellegi-Sunter is the model inside Splink. It answers one question for a pair of records: *how much more likely is what I see if these two records are the same person than if they are two different people?* It builds the answer from four ideas: fields, comparison levels, `m` and `u`.

#### Step 1. Fields

A **field** is one column you compare between the two records. The demo compares seven: canonical first name, surname, date of birth, email, phone, postcode and address (the `comparisons` list in `02_splink.py`). Each field is compared separately, and the results are added up at the end.

#### Step 2. Comparison levels (how well the field agrees)

For each field you do not just ask "same or different?". You define a short ladder of **comparison levels**, also called **agreement levels**, from strongest agreement to disagreement. For the surname in this demo:

| Level | What it means | Example pair |
|---|---|---|
| Missing | one of the two values is empty | `smith` vs (blank) |
| Exact match | identical after standardisation | `smith` vs `smith` |
| Jaro-Winkler ≥ 0.92 | one small typo | `griffiths` vs `griffihs` (0.98) |
| Jaro-Winkler ≥ 0.88 | a bit further apart | `smith` vs `smyth` (0.89) |
| Jaro-Winkler ≥ 0.70 | loosely similar | `walker` vs `walsh` (0.79) |
| All other comparisons | clearly different | `smith` vs `jones` |

Every pair lands on exactly one level per field: Splink checks the levels top to bottom and takes the first one that is true. So a pair of records becomes a short pattern such as *first name exact, surname JW ≥ 0.88, DOB missing, email exact, phone missing, postcode different, address missing*.

#### Step 3. `m`: how often true matches land on this level

`m` is measured **only among pairs that really are the same person**. For each level it is the share of those pairs that land on it.

From the model trained in this demo (`results/splink_model.json`, seed 42; `u` is estimated from a random sample, so your run can differ slightly), for canonical first name:

| Level | m | Read it as |
|---|---|---|
| Exact match | 0.676 | 67.6% of true matches have exactly the same first name |
| JW ≥ 0.92 | 0.176 | 17.6% differ by a small typo |
| JW ≥ 0.88 | 0.025 | 2.5% differ a bit more |
| JW ≥ 0.70 | 0.015 | 1.5% are only loosely similar |
| All other | 0.108 | 10.8% look completely different (swapped first and last name, a nickname not in the dictionary) |

The `m` values of one field add up to 1, because every true match lands somewhere. `m` describes **data quality**: if your sources were perfect, `m` for "exact match" would be 1.0.

#### Step 4. `u`: how often different people land on this level by coincidence

`u` is the same measurement **among pairs of different people**. For the first name, exact match has `u = 0.0047`: two random, unrelated customers share a first name 0.47% of the time, because names like *James* and *Sarah* are common. "All other" has `u = 0.967`: almost all random pairs have clearly different first names.

`u` describes **how common the values are**. A field where everyone has a different value (phone) has a tiny `u` for exact match; a field with few values (gender, city) has a large one.

A useful analogy is a medical test: `m` is the sensitivity (how often the test is positive when the disease is present) and `u` is the false positive rate (how often it is positive when it is not).

#### Step 5. The match weight of one field: log2(m / u)

The ratio `m / u` says how many times more likely the observed level is for a match than for a non-match. Taking `log2` turns it into **bits of evidence**, which can simply be added:

| First-name level | m | u | m / u | Weight log2(m/u) |
|---|---|---|---|---|
| Exact match | 0.676 | 0.0047 | 144 | **+7.2** (strong evidence for a match) |
| JW ≥ 0.70 | 0.015 | 0.025 | 0.6 | **−0.7** (slight evidence against) |
| All other | 0.108 | 0.967 | 0.11 | **−3.2** (evidence against) |
| Missing | | | | **0** (no evidence either way) |

Positive weight means the observation is more typical of matches, negative means more typical of non-matches, and a missing value adds nothing.

#### Step 6. The prior: start from how rare matches are

Before looking at any field, two random records are very unlikely to be the same person. The model's prior is `λ = 0.00022` (about 1 in 4,550 random pairs is a match). As bits: `log2(λ / (1 − λ)) = −12.1`. Every pair starts at −12.1 and the fields have to earn their way up.

#### Step 7. Add everything up and convert to a probability

Total match weight = prior + the weight of each field's level. Convert back with `probability = 2^w / (1 + 2^w)`.

**Example A: the same person in two systems.** CRM has *Robert Smith, 1981-03-14, robert.smith@gmail.com, 07700 900123, SW1A 1AA*. WEB has *Bob Smyth, robert.smith+shop@gmail.com, NW3 2QG* (no DOB, no phone, no address, and he has moved).

| Field | Values after standardisation | Level | m | u | Weight |
|---|---|---|---|---|---|
| Prior | | | | | −12.1 |
| First name | robert / robert (Bob → robert) | Exact | 0.676 | 0.0047 | +7.2 |
| Surname | smith / smyth | JW ≥ 0.88 | 0.036 | 0.00088 | +5.3 |
| DOB | 1981-03-14 / missing | Missing | | | 0 |
| Email | robert.smith@gmail.com both (plus-tag removed) | Exact | 0.785 | 0.00016 | +12.3 |
| Phone | 07700900123 / missing | Missing | | | 0 |
| Postcode | SW1A 1AA / NW3 2QG | All other | 0.278 | 0.965 | −1.8 |
| Address | / missing | Missing | | | 0 |
| **Total** | | | | | **+10.9** |

Probability = 2^10.9 / (1 + 2^10.9) ≈ **0.9995**. The model links them, even with a surname typo and a different postcode, because the email is almost unique to one person.

**Example B: two people in one household.** *Thomas Jones, 2008-07-14* and *Stanley Jones, 2002-07-12*, both with the family email `thejoness@yahoo.co.uk`, the same address and postcode, and different phones.

| Field | Level | Weight |
|---|---|---|
| Prior | | −12.1 |
| First name: thomas / stanley | All other | −3.2 |
| Surname: jones / jones | Exact | +7.4 |
| DOB: 6 years apart | ≤ 10 years | −3.7 |
| Email: same family mailbox | Exact | +12.3 |
| Phone: different | All other | −4.3 |
| Postcode: same | Exact | +12.3 |
| Address: same | Exact | +12.3 |
| **Total** | | **+21.0**, probability ≈ 1.0 |

The model is not wrong about the evidence: a shared email, address and surname really are typical of one person. What it cannot know is that a household shares them too. That is exactly the false merge that the graph step (section 3.7, `04_graph_resolution.py`) catches with a cannot-link rule on DOB.

(The weights above use the trained `m` and `u` before term-frequency adjustment, so the waterfall chart for a real pair can differ slightly.)

#### Step 8. How the model learns `m` and `u` without labels

- **`u` from random pairs.** Pick two records at random and they are almost never the same person (1 in 4,550). So if you sample a few million random pairs and count how often each level occurs, those counts *are* `u`. `estimate_u_using_random_sampling()` does this.
- **`m` with expectation-maximisation (EM).** We do not know which pairs are matches, so EM guesses and refines: (1) start with rough `m` values, (2) score every candidate pair with the current `m` and `u`, giving each a match probability, (3) recompute `m` as the level shares among pairs, weighting each pair by its match probability, (4) repeat until the values stop changing.
- **Why EM runs three times.** Each EM run only looks at pairs from one blocking rule, for example "same DOB". Inside that block every pair agrees on DOB, so the run cannot learn DOB's `m`. `02_splink.py` runs EM on DOB, on postcode and on name blocks, so each field is learned in at least one run.
- **Term-frequency adjustment.** For names and email, Splink replaces the field-average `u` with the frequency of the actual value. Agreeing on `smith` (common, high `u`) earns fewer bits than agreeing on `featherstonehaugh` (rare, tiny `u`).

#### Where to see it in the demo

- `results/splink_m_u_parameters.html`: the `m` and `u` of every level, side by side.
- `results/splink_match_weights.html`: the weight `log2(m/u)` of every level, the same numbers as the tables above.
- `results/splink_waterfall_example.html`: Step 7 for one real pair, bar by bar.
- To print the table yourself:

```powershell
.\.venv\Scripts\python.exe -c "import json, math; m = json.load(open('results/splink_model.json')); [print(c['output_column_name'], l['label_for_charts'], round(l['m_probability'], 4), round(l['u_probability'], 6), round(math.log2(l['m_probability'] / l['u_probability']), 1)) for c in m['comparisons'] for l in c['comparison_levels'] if l.get('m_probability') and l.get('u_probability')]"
```

The assumption to mention in an interview: weights are only allowed to add up because the model treats fields as **independent** given match status. Correlated fields (postcode and address, email and name) are therefore double counted, which is one reason supervised models or careful comparison design can do better.

### 3.6 Supervised matching, step by step

Fellegi-Sunter learns from the data without labels. Supervised matching does the opposite: you show a model pairs whose answer you already know and it learns the rule itself. It is the "ML where deterministic rules are insufficient" in the job description. `03_ml_recordlinkage.py` builds it in five steps.

#### Step 1. The unit of learning is a pair, not a record

A model cannot look at one customer record and say who it is. It looks at **two records** and answers one question: *same person or not?* So every training example is a pair, and its **label** is 1 (match) or 0 (non-match).

The pairs come from the same blocking as the rules matcher (`rules.candidate_pairs`), because scoring all 33.5 million pairs is impossible. That gives 6,405 candidate pairs. The label comes from `true_entity_id`: 1 if both records have the same id. In production that column does not exist; labels come from stewards (Step 7).

One surprise to understand: **88% of the candidate pairs are matches** (5,639 of 6,405), while among all possible pairs only 0.017% are. Blocking has already thrown away almost all the easy non-matches. The model only has to separate the hard cases that survive blocking.

#### Step 2. Features: turn a pair into a row of numbers

A **feature** is one number that describes how the two records compare on one aspect. `features()` builds 14 of them. The same pair, as the model sees it:

| Record | First name | Surname | DOB | Email | Phone | Address | Postcode |
|---|---|---|---|---|---|---|---|
| BILLING-000003 | Thomsa | Datson | 1984-12-28 | (missing) | +44 7890838637 | Sudio 89, Kirsty Oval | SE98 3WD |
| CRM-000004 | Thomas | Dawson | 1984-12-28 | thomas.dawson@btinternet.com | +44 7890838637 | Studio 89, Kirsty Oval | SE98 3WD |

| Feature | What it measures | Value for this pair |
|---|---|---|
| `first_jw` | Jaro-Winkler similarity of canonical first names (0 to 1) | 0.97 (one swapped letter) |
| `last_jw` | Jaro-Winkler of surnames | 0.91 |
| `last_lev` | Levenshtein similarity of surnames | 0.83 |
| `first_phonetic`, `last_phonetic` | Do the Metaphone codes agree? (1/0) | 1 and 0 |
| `dob_exact` | Same DOB? (1/0, empty if either is missing) | 1 |
| `dob_lev` | Character similarity of the DOB strings (catches day/month swaps) | 1.0 |
| `email_qgram`, `email_user_jw` | Similarity of the email and of the part before `@` | 0 (one email is missing) |
| `phone_exact` | Same phone? | 1 |
| `postcode_exact`, `postcode_area_exact` | Same full postcode, same area | 1 and 1 |
| `address_qgram` | q-gram similarity of the street line | 0.91 |
| `record_tfidf_cos` | Cosine similarity of the whole record as character n-grams | 0.59 |
| **Label** | Same `true_entity_id`? | **1** |

The last feature is a cheap "embedding": each record's name, email user, postcode and address are joined into one string, cut into character 2-to-4-grams and weighted by TF-IDF (rare n-grams count more). Two records with the same letters in different places, such as swapped first and last names, still score high.

Notice the design choice in the email row: a missing email scores 0, the same as two completely different emails. Some features (DOB, phone, postcode) keep "missing" as empty instead, and gradient boosting can learn that empty is not the same as disagreeing. That difference matters on real data, where missingness carries information.

#### Step 3. The model: gradient boosting

`HistGradientBoostingClassifier` is a sequence of small decision trees. The first tree makes a rough guess ("same DOB and same phone → likely match"); each next tree concentrates on the pairs the previous ones got wrong ("…unless the first names are completely different"). Three hundred trees later, the sum of their votes is turned into a probability between 0 and 1.

Compared with Fellegi-Sunter:

| | Fellegi-Sunter (Splink) | Gradient boosting |
|---|---|---|
| Needs labels | No | Yes |
| How fields combine | Adds independent bits per field | Learns interactions ("surname agreement matters less when the address also agrees") |
| Correlated fields | Double counted | Handled |
| Inputs | Discrete agreement levels | Any number: similarities, embeddings, business signals |
| Explanation | Waterfall of bits | Feature importance, SHAP values |

#### Step 4. From probability to a decision: the threshold

The model outputs a probability for each pair. A **threshold** turns it into a decision: at or above it the pair becomes an edge (a match), below it not. Edges are then grouped into customers by connected components (section 3.7). The threshold is a business choice, and the cluster metrics show its effect:

| Threshold | Pair precision | Pair recall | Largest cluster |
|---|---|---|---|
| 0.5 | 0.968 | 0.976 | 9 |
| 0.9 (used) | 0.976 | 0.975 | 7 |
| 0.99 | 0.981 | 0.974 | 7 |

Raising the threshold removes false edges, but even at 0.99 there are still false merges. Those are pairs the model is *sure* about and wrong about (Step 6), which no threshold can fix.

#### Step 5. Evaluate without fooling yourself

Three traps, and what the demo does about each:

- **Accuracy is meaningless here.** With 88% matches, a model that always says "match" is 88% accurate. Report **average precision** (how well the model ranks matches above non-matches) and, above all, cluster metrics.
- **Leakage between train and test.** One person appears in many pairs. If you split pairs at random, 74% of test pairs share a record with a training pair, so the model is partly tested on people it has already seen. The fix is to split **by person**: `03` scores each pair with a model trained on the other half of the people (by the left record), and `08` uses a strict split where a person is entirely in train or entirely in test. On this synthetic data both splits give an average precision of about 0.9999, because the task is easy; on real data the random split is the one that flatters you.
- **Pair metrics hide cluster errors.** Out-of-fold average precision is 0.9998, almost perfect. Yet after grouping, 142 pairs of records are wrongly in the same customer. That is why every method in this demo is compared on B-cubed and false-merge pairs, not on pair scores.

#### Step 6. Confidence: is p = 0.9 really 90%?

A probability is only useful for thresholds and review queues if it is **calibrated**: among all pairs scored around 0.9, about 90% should be matches. `08_mlops_feature_store.py` checks this on the held-out people by grouping pairs into ten probability bins and comparing the average prediction with the share that really matched:

| Predicted probability bin | Pairs | Average prediction | Share that really matched |
|---|---|---|---|
| 0.0 to 0.1 | 94 | 0.002 | 0.085 |
| 0.1 to 0.9 | 7 | (mixed) | (too few to judge) |
| 0.9 to 1.0 | 1,948 | 1.000 | 0.997 |

- **ECE (expected calibration error)** is the weighted average gap between those two columns: 0.004 for gradient boosting, 0.012 for logistic regression. Below about 0.05 is good.
- **Brier score** is the mean of (prediction − label)²: 0.003.
- The model is extremely confident: almost every pair is below 0.1 or above 0.9. The 8 true matches hiding in the bottom bin are missed matches, and the 6 non-matches at the top are the confident mistakes from Step 4.

#### Step 7. Where it fails, and where labels come from

The confident mistakes are worth showing in an interview, because they are the cases no model trained on these fields can solve:

| Pair | Why the model says match (p = 1.0) | Truth |
|---|---|---|
| Robert Williams, 1996-12-13 / Ronald Williams, 1996-12-13 | Same surname and DOB, similar first name | Two people |
| Craig Jones, craig.jones@gmail.com / Craig Jones, craig.jones@gmail.com | Same name and email | Two people (a generated email collision) |

These need either more signals (a verified email, a loyalty id) or a human: they belong in the review queue.

**Where labels come from in production.** What you label is a *pair*, not a record and not a feature: the features are computed automatically from the two records, and the label is a human or a trusted source saying "same person" (1) or "not the same person" (0). Real projects mix three sources:

| Source | What it is | Strength | Weakness |
|---|---|---|---|
| **Human review** | Stewards decide pairs from the review queue; every decision is stored as a labelled pair. A **golden set** of a few thousand pairs, sampled across score bands, is labelled once and kept for evaluation. | Most reliable; covers the hard cases | Expensive: hundreds or a few thousand pairs, not millions |
| **Silver labels** | Links the business already trusts: same national ID, tax number or passport, same loyalty card, one login used in both systems, merges stewards already approved in the MDM | Free and plentiful | Biased towards easy pairs, so add human-reviewed hard pairs on top |
| **Unsupervised model as teacher** | Pairs Splink scores very high or very low become provisional labels; people check the grey zone | Gets a classifier started on day one | Inherits the teacher's mistakes (households!) |

**Active learning** (Zingg, dedupe) keeps the human part small: the model sends people only the pairs it is least sure about (scores near 0.5), because a pair it already gets right teaches it nothing. 50 well-chosen labels can do the work of 5,000 random ones.

**What about synthetic data?** This demo's `true_entity_id` is synthetic, and that is fine for building and testing the pipeline and for showing the method. It is not a substitute for real labels: the errors in real data (how people actually mistype, how systems truncate names, which fields go missing together) differ from the errors you invented, so a model trained only on synthetic pairs can score well here and still fail on production data.

**A sensible path:** start with Splink, which needs no labels; store every steward decision as a label from day one; use active learning to spend reviewer time on hard pairs; bring in the supervised model once a golden set of a few thousand real pairs shows it beats Splink on *cluster* metrics.

### 3.7 Clustering and the graph view, step by step

Every matcher in sections 3.4 to 3.6 answers a question about **two** records. A customer can have five records across three systems. Turning pair decisions into customers is a graph problem, and it is where most real false merges come from. `04_graph_resolution.py` implements this section.

#### Step 1. Records are nodes, matches are edges

Draw every record as a dot (a **node**). For every pair the model accepts, draw a line between the two dots (an **edge**). Give each edge a **weight**: how strong the evidence is. In this demo the weight is the Splink match weight in bits from section 3.5 (for the ML model, the log-odds of its probability in bits).

Why bits and not the probability? Probabilities saturate. An edge with 15 bits of evidence has p = 0.99997 and an edge with 60 bits has p = 0.999…9; both print as 1.0, but the second is enormously stronger. Bits keep that difference visible.

#### Step 2. A customer is a connected component

A **connected component** is a group of nodes that can all reach each other by following edges. If A matches B and B matches C, then A, B and C are one component, and so one customer, even if A and C were never compared. This step is called **transitive closure**; `union_find_clusters()` and Splink's clustering both do it.

On this data the Splink edges at p ≥ 0.95 form components of these sizes:

| Records in component | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|
| Number of components | 1,452 | 1,463 | 971 | 193 | 12 | 8 | 3 |

Nobody in the generator has more than 6 records, so a component of 7 is certainly wrong.

#### Step 3. Chaining: why one bad edge is enough

Matching is **not transitive** in reality: A looks like B and B looks like C does not prove A is C. Transitive closure assumes it is. So one false edge between two genuine customers merges *all* their records. This is **chaining**, and it is why pair metrics can look perfect while customers are wrong.

A real component from the demo, all edges accepted by Splink:

```text
  Thomas Jones  CRM-000035   2008-07-14  FY15 6JF  thejoness@yahoo.co.uk
  Thomas Jons   BILLING-000036  (no DOB) FY15 6JF  thejoness@yahoo.co.uk
  Stanley Jones WEB-005154   2002-07-12  FY15 6JF  thejoness@yahoo.co.uk
  Stanley Jones WEB-005155   2002-07-12  FY15 6JF  thejoness@yahoo.co.uk
  Stanley Jones BILLING-005156 (no DOB)  WD2P 8EJ  thejoness@yahoo.co.uk

  edges (bits):  WEB-005154 -- WEB-005155      59.5   (identical records)
                 CRM-000035 -- BILLING-000036  34.1
                 BILLING-000036 -- WEB-005154/5 25.3 each
                 CRM-000035 -- WEB-005154/5    15.3 each
                 BILLING-005156 -- WEB-005154/5 6.6 each
```

Thomas and Stanley are two people in one household with a family mailbox. Every edge is individually plausible, and together they make one 5-record "customer".

#### Step 4. Cannot-link constraints: business knowledge the model lacks

A **cannot-link constraint** is a rule that says two records are definitely *different* people, whatever the score. `cannot_link()` uses two:

| Rule | Fires when | Does not fire when |
|---|---|---|
| `dob_conflict()` | both DOBs are known and different | one DOB is missing, or the two are a day/month swap (03/04 vs 04/03) |
| `name_conflict()` | canonical first names clearly differ (Jaro-Winkler < 0.75 and different Metaphone) | the DOB matches (a typo'd nickname), or the names look swapped between first and last |

In the component above, Thomas (2008-07-14) and Stanley (2002-07-12) break the DOB rule, and *thomas* vs *stanley* breaks the name rule. The component holds six conflicting pairs, so it must be split. Of 2,712 multi-record Splink components, 42 contain a conflict.

#### Step 5. Minimum cut: remove the weakest edges that separate them

Given two records that must end up apart, which edges do you delete? The **minimum cut** answers it: the set of edges whose removal disconnects the two records with the smallest total weight. Think of the edges as pipes and the weight as their width: the min cut is the cheapest set of pipes to block so nothing flows from one record to the other. `nx.minimum_cut` computes it with the edge weights as **capacities**.

`repair()` runs it on one conflicting pair, removes the cut edges, and checks each piece again until no piece contains a conflict. For the Jones component:

1. Cut 1 separates BILLING-005156 from the rest by removing its two 6.6-bit edges (total 13.2 bits, the cheapest way out).
2. Cut 2 separates the two Stanley web records from the two Thomas records by removing the four 15.3- and 25.3-bit edges between them.
3. The identical Stanley records (59.5 bits) are never cut.

Result: {Thomas CRM, Thomas BILLING}, {Stanley WEB, Stanley WEB} and {Stanley BILLING} alone. The household is no longer one customer. The last record is an over-split: it really is Stanley, but its only evidence was the family email and surname, so the safe choice is to leave it as its own customer for the review queue. Splitting too much is recoverable; merging two people is not.

Across the whole data set, 80 edges are cut in 42 components:

| Splink clusters | Pair precision | Pair recall | B-cubed F1 | False-merge pairs |
|---|---|---|---|---|
| Connected components | 0.966 | 0.965 | 0.985 | 198 |
| + cannot-link and min cut | 0.998 | 0.962 | 0.989 | 12 |

#### Step 6. The identifier graph: who shares an email?

A second graph uses **identifiers** as nodes too: every email and every phone becomes a node connected to the records that carry it. After resolution, an identifier connected to records of **more than one customer** is suspicious. `shared_identifiers()` lists them: 48 emails and 25 phones.

- 31 of the 48 emails really are shared by different people: family mailboxes such as `thejoness@yahoo.co.uk`. These should be excluded from blocking and given less weight in matching (the "generic identifier" list).
- The other emails and all 25 phones belong to one person whose records ended up as two customers: they are **missed matches**, and the list is a ready-made work queue for stewards.

#### Step 7. Hierarchies are graphs too

The same idea builds households in `06_customer_spine.py`: customers and addresses are nodes, "this customer has lived at this address" is an edge, and each connected component is a household. A graph is the natural model for any "belongs to" structure: person → household, person → company, company → group.

#### Step 8. Other graph techniques worth naming

| Technique | What it does | When to use it |
|---|---|---|
| Edge betweenness, bridges | Finds edges that many shortest paths cross: likely bridges between two real clusters | Spotting chaining without constraints |
| Community detection (Louvain, Leiden) | Splits a graph into densely connected groups | Very large components, no clear constraints |
| Correlation clustering | Chooses clusters that disagree least with all positive and negative pair scores | When you trust the negative scores as well |
| Cluster density | Share of possible edges inside a cluster that exist | A cheap alarm: a 6-record cluster with 5 edges is a chain, not a clique |
| GraphFrames / Spark | Connected components on hundreds of millions of edges | Production scale; repair only the few components that hold a conflict |
| Neo4j, TigerGraph | Graph database with online traversal | When the hierarchy is queried live by applications |

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

#### Precision or recall: which matters more?

For customer identity, **precision** usually matters more. But the real answer is that you choose the threshold from the cost of each kind of error, and that depends on what the matches are used for.

| Error | What it means | Consequence | Can you undo it? |
|---|---|---|---|
| Low precision: **false merge** | Two different people become one customer | One person sees another's orders, address or account (a GDPR incident); marketing consent, credit and fraud decisions run on mixed data | Hard: downstream systems have already used the merged customer |
| Low recall: **missed match** | One person has two customer ids | Duplicate letters, a less complete customer view, slightly worse analytics | Easy: a later run or a steward links them |

That is why the graph step trades 0.3 points of recall (0.965 → 0.962) for precision going from 0.966 to 0.998, and why section 3.7 says splitting too much is recoverable but merging two people is not.

Use cases where **recall** wins:

- **Fraud and AML:** missing that two applications come from the same person is the expensive mistake; an analyst removes the false matches.
- **Sanctions screening and KYC:** a missed match can be a regulatory breach.
- **GDPR subject access or erasure:** you must find every record of the person.

In practice you use **two thresholds**, not one: above the high threshold pairs merge automatically (protects precision), between the two they go to the steward review queue (recovers recall), below the low one they stay apart. And measure on **clusters** (B-cubed), plus the number of false-merge pairs and the largest cluster, not only on pairs: one bad pair can merge two whole customers. The ML matcher shows it: average precision 0.9998, yet 142 false-merge pairs.

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

1. `build_graph()` makes a networkx graph: records are nodes, accepted pairs are edges weighted by the evidence in bits (Splink's match weight).
2. `cannot_link()` combines two rules. `dob_conflict()`: both DOBs known and different, allowing a day/month swap. `name_conflict()`: canonical first names clearly different (Jaro-Winkler < 0.75, different metaphone), with no matching DOB and no sign of swapped first/last names.
3. `repair()` checks every component. When it finds a conflicting pair it runs `nx.minimum_cut` between them with the evidence in bits as capacities (`evidence_bits()` converts an ML probability to log-odds), removes the cut edges, and re-checks both sides until no conflict remains. Section 3.7 walks through a real example.
4. `shared_identifiers()` builds the identifier view: every email or phone that points at more than one resolved person.

**What to explain:** for Splink, 42 components are split by cutting 80 edges; false-merge pairs drop from 198 to 12 and recall falls only from 0.965 to 0.962. For ML, false merges drop from 142 to 9 and B-cubed F1 rises to 0.992, the best in the demo. The constraints are business rules, so they are easy to explain and to audit. The shared-identifier list is a steward work queue and a candidate list of values to exclude from blocking.

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
- **Explain Fellegi-Sunter in one minute.** "For each field I define agreement levels: exact, small typo, different, missing. `m` is how often true matches land on a level, `u` how often different people land on it by chance. The weight is log2(m/u), in bits. I start from the prior, about −12 bits because matches are rare, add each field's bits and convert to a probability. `u` comes from random pairs and `m` from EM, so no labels are needed." Section 3.5 has the worked examples.
- **What does term-frequency adjustment do?** Agreement on a rare surname counts more than on `Smith`, using the value's frequency.
- **Are Splink and Zingg commercial? Do you need a licence?** No. Splink (UK Ministry of Justice) is MIT-licensed, free for any use including commercial. Zingg has a free Community edition under AGPL-3.0 and a paid Zingg Enterprise edition with extra features and support; AGPL is fine for internal use, and its obligations apply only if you modify Zingg and distribute it or offer it as a service, which is why some legal teams avoid it. Everything else in the demo (rapidfuzz, recordlinkage, networkx, DuckDB, scikit-learn) is MIT or BSD. The commercial products in this space are Senzing, Informatica, Reltio, Tamr and Quantexa.
- **Jaro-Winkler or Levenshtein?** Jaro-Winkler for short strings like names (rewards common prefixes); Levenshtein or edit distance for codes and longer strings; token-based ratios when word order varies.

### Graphs

- **Where do graphs help in identity resolution?** Clustering (components), chaining detection and repair, shared identifiers, households and company hierarchies, propagating identity across sources that never share a field directly.
- **Matching is not transitive. What do you do?** Evaluate clusters, cap or inspect large components, add cannot-link constraints, cut the weakest edges (min cut), or use correlation clustering or community detection.
- **How would you scale the graph step?** GraphFrames connected components on Spark; repair only components that contain a conflict, which is a small fraction; a graph database only for online traversal.

### ML and confidence

- **Where do labels come from? Do you need synthetic data?** You label pairs, not features. Sources: steward decisions on the review queue and a stratified golden set; silver labels from identifiers the business already trusts (national ID, loyalty card, shared login); high- and low-scoring Splink pairs as provisional labels; active learning to send people only the most uncertain pairs. Synthetic data is for building and testing the pipeline, not for training the production model. Section 3.6, Step 7.
- **How do you avoid leakage?** Split by entity, never by pair; `08` shows the strict split.
- **What does "confidence" mean for a match?** A calibrated probability. Check calibration (Brier, ECE) before using thresholds; recalibrate with isotonic or Platt scaling.
- **Precision or recall?** Usually precision: a false merge can expose one person's data to another and corrupt consent and credit decisions, and it is hard to undo, while a missed match is a duplicate a later run can fix. Recall wins for fraud, AML, sanctions screening and GDPR access requests. Use two thresholds (auto-merge, review queue, keep apart) and measure on clusters. Section 3.9.

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
| Field | One column compared between two records (surname, DOB, email...) |
| Comparison (agreement) level | One rung of a field's similarity ladder: exact, small typo, different, missing |
| m probability | Share of true matches that land on a level (data quality) |
| u probability | Share of different-person pairs that land on a level by chance (how common the value is) |
| Match weight | log2(m/u), summed over fields plus the prior |
| EM | Expectation-maximisation: estimates `m` without labels |
| B-cubed | Per-record cluster precision and recall |
| Chaining | One bad edge merging two clusters through transitive closure |
| Feature | One number describing how two records compare on one aspect |
| Label | The known answer for a training pair: match (1) or non-match (0) |
| Calibration | Whether predicted probabilities match observed match rates |
| Connected component | A group of nodes that can all reach each other through edges |
| Transitive closure | Treating A=B and B=C as A=C, i.e. taking connected components |
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
