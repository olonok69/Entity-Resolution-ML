# Video script: Customer identity resolution, from fuzzy matching to a governed customer spine

A recording plan for the YouTube video built on this repository. Target length about 18 minutes. Each chapter lists what is on screen and what to say; the narration is a guide, not a teleprompter. Numbers come from a clean run with seed 42; re-run `run_all.sh` before recording and check them against `results/comparison.md`.

The slide deck [`slides/customer-identity-resolution.pptx`](slides/customer-identity-resolution.pptx) follows the same chapters, so slides can be cut in between the screen recordings.

## Before recording

- Fresh run: `bash run_all.sh` (or the PowerShell sequence in [DEMO_GUIDE.md](DEMO_GUIDE.md)).
- Open in browser tabs: `results/comparison.md` (rendered), `results/splink_waterfall_example.html`, `results/splink_match_weights.html`.
- Open a DuckDB shell or DBeaver on `results/mdm.duckdb` with the queries from README section 3 ready.
- Editor font size 16+, terminal font size 16+, hide notifications.
- Keep `true_entity_id` visible in the first data shot only, and say once that it is the answer key, never a matching field.

## Chapters (YouTube description)

```text
00:00 Why customer identity is hard
01:30 The synthetic data and why it has an answer key
03:00 Standardisation and blocking
05:00 Rules and fuzzy matching
06:30 Splink: Fellegi-Sunter without labels
09:30 Supervised ML and why pair metrics lie
10:30 Graphs: cannot-link constraints and min-cut repair
12:30 MDM: golden record, crosswalk, stewardship
14:00 Customer spine and the identity hierarchy
15:00 Identity drift: keeping ids stable
16:00 MLOps: feature store, registry, monitoring
17:15 Summary and what production needs
```

## 1. Why customer identity is hard (00:00, 1.5 min)

**On screen:** title slide, then three tables side by side: CRM, WEB, BILLING rows for the same person with different spellings.

**Say:** "Every company has the same customer in several systems, and none of them share a key. Robert Smith in the CRM is Bob Smith on the website and R. Smyth in billing. If you get it wrong one way you send three letters; if you get it wrong the other way you merge two people and show one customer another's data. In this video I build the whole pipeline on a laptop: fuzzy matching, a probabilistic model, machine learning, graph techniques, a small master data hub, a governed customer spine, and the MLOps around it, and I measure every step."

## 2. The data and the answer key (01:30, 1.5 min)

**On screen:** `data/generate_data.py` (`noisy_copy`, `add_households`), then `data/customers.csv` in a viewer.

**Say:** "Real data never tells you the truth, so I generate it. 4,000 people, 8,192 records across three systems, with typos, nicknames, swapped names, missing fields, people who moved house, and 183 households where two people share an address and sometimes a family email. Each record keeps a `true_entity_id`. It is the answer key: I only use it to measure, never to match."

## 3. Standardisation and blocking (03:00, 2 min)

**On screen:** `common/standardise.py` (nicknames, `clean_email`, `clean_phone`), then `BLOCKING_KEYS` in `01_rules_rapidfuzz.py` and the printed blocking line.

**Say:** "Half of matching quality comes from boring cleaning: lowercase, remove titles, map Bob to Robert, normalise phone numbers and postcodes, add phonetic codes. Then blocking. 8,192 records make 33.5 million pairs. I only compare records that share a cheap key: same email, same phone, same DOB and surname sound, and so on. That leaves 6,405 pairs, and they still contain 96.5% of the true matches. That number is the ceiling on recall, so it is the first thing I measure."

## 4. Rules and fuzzy matching (05:00, 1.5 min)

**On screen:** `score()` in `01_rules_rapidfuzz.py`, then the metrics line.

**Say:** "The classic approach: a weighted fuzzy score, two thresholds for auto-match and review, and Union-Find to turn pairs into customers. F1 is 0.93. It is easy to explain, but I picked every weight by hand, and every new source means re-tuning."

## 5. Splink: Fellegi-Sunter without labels (06:30, 3 min)

**On screen:** the two Fellegi-Sunter slides (fields, levels, m and u; then the bits adding up), `train()` in `02_splink.py`, then `splink_m_u_parameters.html`, then `splink_match_weights.html` and `splink_waterfall_example.html`.

**Say:** "Splink learns the weights instead of me guessing them. It compares the two records one field at a time: first name, surname, date of birth, email and so on. For each field it has a small ladder of agreement levels: exact, a small typo, further apart, completely different, or missing.

For every level it learns two numbers. m: of all the pairs that really are the same person, how many land on this level? For the first name, 68% agree exactly. u: of all the pairs that are different people, how many land on it just by coincidence? Only half a percent share a first name. Divide m by u, take log base 2, and you get bits of evidence: plus 7 for an exact first name, minus 3 for a different one, zero if it is missing.

Every pair starts at minus 12 bits, because only one random pair in four and a half thousand is a match. Add the bits for each field, convert to a probability, done. u comes from random pairs, which are almost never matches, and m from expectation-maximisation, so I need no labels at all. And it explains itself: this waterfall chart is exactly that sum, bar by bar, for one pair.

Precision is 0.966, which is lower than I expected. When I look at the false merges, 110 of the 198 are people from the same household. Same address, same surname, same family email. The model is right that this is strong evidence; it is just evidence for a household, not for a person. Keep that in mind."

## 6. Supervised ML and why pair metrics lie (09:30, 1 min)

**On screen:** `features()` in `03_ml_recordlinkage.py`, then the printed AP and cluster metrics.

**Say:** "If stewards give me labels, I can train a classifier on pair features. Average precision is 0.9998, basically perfect. But turn pairs into clusters and there are still 142 wrong pairs, because one bad edge joins two whole clusters. That is why I always evaluate clusters with B-cubed, not just pairs."

## 7. Graphs: cannot-link and min-cut repair (10:30, 2 min)

**On screen:** diagram slide of a chained cluster with a cut, `repair()` and `cannot_link()` in `04_graph_resolution.py`, the before/after lines, then `shared_identifiers.csv`.

**Say:** "Think of records as nodes and matches as edges. A customer is a connected component. Now add business knowledge: two records with different dates of birth cannot be the same person. When a component contains such a pair, I run a minimum cut: the cheapest set of edges that separates them. The weak bridge goes, the strong core stays. False-merge pairs drop from 198 to 12, and recall only moves from 0.965 to 0.961.

The same graph gives me something else: emails connected to more than one person. Here 31 of them are family mailboxes. That list goes to the stewards and into the blocking exclusion list."

## 8. MDM: golden record, crosswalk, stewardship (12:30, 1.5 min)

**On screen:** DuckDB queries on `golden_record` (show `provenance`), `xref`, `golden_history`, `review_queue`.

**Say:** "Clusters are not a product yet. The master data hub gives every customer a stable id, picks the best value of every field with survivorship rules and records where it came from, keeps a crosswalk from every source id, and keeps history. New records are scored against the master with the saved model: 197 of 200 returning customers attached correctly. Uncertain ones go to a review queue, and every steward action is audited. GDPR erasure removes a person from every table."

## 9. Customer spine and hierarchy (14:00, 1 min)

**On screen:** `SELECT * FROM customer_spine WHERE household_size > 1`, the hierarchy query, and `spine_contracts.csv`.

**Say:** "The customer spine is the one table everybody joins to. Each row is a customer with its household, its source keys, the model version and the weakest link. Above it, a governed hierarchy: household, customer, source record, each edge with its rule and confidence. And governance is code: seven data contracts run on every build, and if one fails, nothing is published."

## 10. Identity drift (15:00, 1 min)

**On screen:** identity drift slide (bar chart), `carry_forward()` in `07_identity_drift.py`.

**Say:** "Run the matching again next week and see what happens to the ids. Renumber the clusters and 56% of customers get a new id: every downstream table breaks. Carry the ids forward by overlap, keep the id for the largest part of a split, and keep an alias when two customers merge, and only 0.2% change."

## 11. MLOps: feature store, registry, monitoring (16:00, 1.25 min)

**On screen:** `FeatureStore` class, the registry and promotion lines, then `monitoring_report.csv`.

**Say:** "To run the ML matcher as a product, features live in a versioned feature store that training and scoring both read, so there is no skew. Models go into a registry; a challenger only becomes champion if it passes a gate on cluster quality and calibration. Then monitoring without labels: on a normal batch the score distribution is stable. On a broken feed, where phone numbers vanished and names became initials, four drift alerts fire, while the match rate on its own looks better. Watch more than one KPI."

## 12. Summary (17:15, 1 min)

**On screen:** results summary slide, then the repository URL.

**Say:** "Rules are explainable, Splink gives you learned weights without labels, ML gives you recall when you have labels, and graphs fix what pairs cannot see. Around that you need a master, a governed spine, stable ids and MLOps. Everything is in the repository, with a guide that explains every step. In production, expect messier data and lower numbers; the method is what carries over."

## B-roll and graphics list

- Three-system animation of one person's records (chapter 1).
- Blocking funnel: 33.5M → 6,405 pairs (chapter 3).
- Fellegi-Sunter weights adding up (chapter 5).
- Chained cluster with a red min-cut edge (chapter 7).
- Household → customer → source tree (chapter 9).
- Drift bar chart: 56% / 0.87% / 0.20% (chapter 10).
- Results table from `results/comparison.md` (chapter 12).
