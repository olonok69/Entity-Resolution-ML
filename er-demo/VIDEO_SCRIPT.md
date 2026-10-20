# Video script: Customer identity resolution, from fuzzy matching to a governed customer spine

A recording plan for the YouTube video built on this repository. Target length about 22 minutes. Each chapter lists what is on screen and what to say; the narration is a guide, not a teleprompter. Numbers come from a clean run with seed 42; re-run `run_all.sh` before recording and check them against `results/comparison.md`.

Record from this script, not from the guide. The slide deck [`slides/customer-identity-resolution.pptx`](slides/customer-identity-resolution.pptx) runs in the same order as the chapters below: each chapter lists its slides, so you can go through the deck from slide 1 to 29 without jumping. Each chapter also names the [DEMO_GUIDE.md](DEMO_GUIDE.md) section to link in the video description for viewers who want the details.

## Before recording

- Fresh run: `bash run_all.sh` (or the PowerShell sequence in [DEMO_GUIDE.md](DEMO_GUIDE.md)).
- Open in browser tabs: `results/comparison.md` (rendered), `results/splink_waterfall_example.html`, `results/splink_match_weights.html`.
- Open a DuckDB shell or DBeaver on `results/mdm.duckdb` with the queries from README section 3 ready.
- Editor font size 16+, terminal font size 16+, hide notifications.
- Keep `true_entity_id` visible in the first data shot only, and say once that it is the answer key, never a matching field.

## Chapters (YouTube description)

```text
00:00 Why customer identity is hard
02:00 The synthetic data and why it has an answer key
03:30 Standardisation and blocking
05:30 Rules and fuzzy matching
07:00 Splink: Fellegi-Sunter without labels
10:00 Supervised ML: features, labels and why pair metrics lie
12:00 Precision or recall? Pricing each error
13:00 Graphs: chaining, cannot-link constraints and min-cut repair
15:30 MDM: golden record, crosswalk, stewardship
17:00 Customer spine and the identity hierarchy
18:00 Identity drift: keeping ids stable
19:00 MLOps: feature store, registry, monitoring
20:15 From a laptop to a data platform
21:30 Summary and what production needs
```

## Slide order at a glance

| Chapter | Slides | Guide section |
|---|---|---|
| 1. Why customer identity is hard | 1 to 4 | 3.1 |
| 2. The data and the answer key | 5 | 4 (generate_data.py) |
| 3. Standardisation and blocking | 6 to 7 | 3.2, 3.3 |
| 4. Rules and fuzzy matching | 8 | 3.4 |
| 5. Splink | 9 to 10 | 3.5 |
| 6. Supervised ML | 11 to 12 | 3.6 |
| 7. Precision or recall? | 13 | 3.9 |
| 8. Graphs | 14 to 17 | 3.7 |
| 9. MDM | 18 to 19 | 3.8 |
| 10. Customer spine | 20 | 3.8 |
| 11. Identity drift | 21 | 3.10 |
| 12. MLOps | 22 to 24 | 3.11 |
| 13. From a laptop to a data platform | 25 to 26 | 7 |
| 14. Summary | 27 to 29 | 2 |

## 1. Why customer identity is hard (00:00, 2 min)

**Slides:** 1 (title), 2 (one person, three systems), 3 (what you will learn), 4 (the pipeline).

**On screen:** slides 1 and 2, with the CRM, WEB and BILLING rows for the same person; then slides 3 and 4.

**Say:** "Every company has the same customer in several systems, and none of them share a key. Robert Smith in the CRM is Bob Smith on the website and R. Smyth in billing. If you get it wrong one way you send three letters; if you get it wrong the other way you merge two people and show one customer another's data. In this video I build the whole pipeline on a laptop: fuzzy matching, a probabilistic model, machine learning, graph techniques, a small master data hub, a governed customer spine, and the MLOps around it, and I measure every step.

Here is the map of the video [slide 3]. And here is the pipeline [slide 4]: eight stages, the same shape every time. Standardise, block, score, graph, master, spine, stabilise, operate. Each box is one script in the repository."

## 2. The data and the answer key (02:00, 1.5 min)

**Slides:** 5.

**On screen:** slide 5, then `data/generate_data.py` (`noisy_copy`, `add_households`), then `data/customers.csv` in a viewer.

**Say:** "Real data never tells you the truth, so I generate it. 4,000 people, 8,192 records across three systems, with typos, nicknames, swapped names, missing fields, people who moved house, and 183 households where two people share an address and sometimes a family email. Each record keeps a `true_entity_id`. It is the answer key: I only use it to measure, never to match."

## 3. Standardisation and blocking (03:30, 2 min)

**Slides:** 6 (Matching section), 7 (blocking funnel).

**On screen:** slide 6, then `common/standardise.py` (nicknames, `clean_email`, `clean_phone`), then `BLOCKING_KEYS` in `01_rules_rapidfuzz.py`, the printed blocking line and slide 7.

**Say:** "Half of matching quality comes from boring cleaning: lowercase, remove titles, map Bob to Robert, normalise phone numbers and postcodes, add phonetic codes. Then blocking. 8,192 records make 33.5 million pairs. I only compare records that share a cheap key: same email, same phone, same DOB and surname sound, and so on. That leaves 6,405 pairs, and they still contain 96.5% of the true matches. That number is the ceiling on recall, so it is the first thing I measure."

## 4. Rules and fuzzy matching (05:30, 1.5 min)

**Slides:** 8 (three ways to score a pair).

**On screen:** slide 8, then `score()` in `01_rules_rapidfuzz.py`, then the metrics line.

**Say:** "The classic approach: a weighted fuzzy score, two thresholds for auto-match and review, and Union-Find to turn pairs into customers. F1 is 0.93. It is easy to explain, but I picked every weight by hand, and every new source means re-tuning. That is why the next two chapters replace the hand-picked weights: Splink learns them without labels, and a classifier learns them from labels."

## 5. Splink: Fellegi-Sunter without labels (07:00, 3 min)

**Slides:** 9 (fields, levels, m and u), 10 (adding up the bits for one pair).

**On screen:** slide 9, then `train()` in `02_splink.py`, then `splink_m_u_parameters.html`, then slide 10 next to `splink_match_weights.html` and `splink_waterfall_example.html`.

**Say:** "Splink learns the weights instead of me guessing them. It compares the two records one field at a time: first name, surname, date of birth, email and so on. For each field it has a small ladder of agreement levels: exact, a small typo, further apart, completely different, or missing.

For every level it learns two numbers. m: of all the pairs that really are the same person, how many land on this level? For the first name, 68% agree exactly. u: of all the pairs that are different people, how many land on it just by coincidence? Only half a percent share a first name. Divide m by u, take log base 2, and you get bits of evidence: plus 7 for an exact first name, minus 3 for a different one, zero if it is missing.

Every pair starts at minus 12 bits, because only one random pair in four and a half thousand is a match. Add the bits for each field, convert to a probability, done. u comes from random pairs, which are almost never matches, and m from expectation-maximisation, so I need no labels at all. And it explains itself: this waterfall chart is exactly that sum, bar by bar, for one pair.

Precision is 0.966, which is lower than I expected. When I look at the false merges, 110 of the 198 are people from the same household. Same address, same surname, same family email. The model is right that this is strong evidence; it is just evidence for a household, not for a person. Keep that in mind."

## 6. Supervised ML: features, labels and why pair metrics lie (10:00, 2 min)

**Slides:** 11 (a pair becomes a row of features), 12 (where labels come from).

**On screen:** slide 11, `features()` in `03_ml_recordlinkage.py`, the printed AP and cluster metrics, then slide 12.

**Say:** "If stewards give me labels, I can train a classifier instead. Each candidate pair becomes one row of numbers: how similar the first names are, the surnames, does the date of birth agree, the phone, the postcode, and a TF-IDF similarity of the whole name. For Thomsa Datson and Thomas Dawson that is 0.97 for the first name, 0.91 for the surname, and ones for date of birth, phone and postcode. The label is one if they are the same person. Gradient boosting learns from those rows, and unlike Fellegi-Sunter it can learn combinations, like a shared phone meaning less when the surname is different.

Two traps. Split train and test by person, not by pair, or the same record appears on both sides and the score is too good. And check calibration: when the model says 0.9, is it right nine times in ten? Here it is, with an error of 0.4 points. Average precision is 0.9998, basically perfect. But turn pairs into clusters and there are still 142 wrong pairs, because one bad edge joins two whole clusters. That is why I always evaluate clusters with B-cubed, not just pairs.

Where do labels come from in real life? Not from synthetic data like mine. You label pairs: stewards decide grey-zone pairs from the review queue, the business already trusts some links, like the same passport or loyalty card, and Splink's very high and very low scores can start you off. Active learning sends people only the pairs the model is least sure about. And everything here is open source: Splink is MIT, Zingg's community edition is AGPL, no licence to buy."

## 7. Precision or recall? (12:00, 1 min)

**Slides:** 13.

**On screen:** slide 13.

**Say:** "Which error is worse? For customer data, usually the false merge: two people become one, one sees the other's orders, and that is a privacy incident that is hard to undo. A missed match is a duplicate letter that a later run can fix. But not always: for fraud, sanctions screening or a GDPR access request, missing a link is the expensive mistake. So you don't pick one threshold, you pick two: above the high one merge automatically, in the middle send it to a person, below the low one keep apart."

## 8. Graphs: chaining, cannot-link and min-cut repair (13:00, 2.5 min)

**Slides:** 14 (Graphs section), 15 (one bad edge merges two people), 16 (cannot-link and minimum cut), 17 (minimum cut on the Jones component).

**On screen:** slides 14 and 15, then 16 and 17, `repair()` and `cannot_link()` in `04_graph_resolution.py`, the before/after lines, then `shared_identifiers.csv`.

**Say:** "Think of records as nodes and matches as edges, and give every edge its evidence in bits, the same match weight Splink computed. A customer is a connected component: everything you can reach by following edges. That is also the danger. If A matches B and B matches C, A and C end up together even if they share nothing. Here is a real one: two Thomas Joneses and three Stanley Joneses, joined by one weak 6.6-bit edge from a shared family email.

Now add business knowledge as cannot-link rules: two records with different dates of birth cannot be the same person. 42 of the 2,712 components break a rule. For each one I run a minimum cut: the set of edges with the fewest total bits that separates the conflicting records. The 6.6-bit bridge goes, the 59.5-bit edge between the two identical Thomas records never does. Using bits matters: probabilities all saturate near 1, so the cut could not tell a strong edge from a weak one. 80 edges are cut, false-merge pairs drop from 198 to 12, and recall only moves from 0.965 to 0.962.

The same graph gives me something else: emails connected to more than one person. Here 31 of them are family mailboxes. That list goes to the stewards and into the blocking exclusion list."

## 9. MDM: golden record, crosswalk, stewardship (15:30, 1.5 min)

**Slides:** 18 (Mastering section), 19 (the mini MDM).

**On screen:** slides 18 and 19, then DuckDB queries on `golden_record` (show `provenance`), `xref`, `golden_history`, `review_queue`.

**Say:** "Clusters are not a product yet. The master data hub gives every customer a stable id, picks the best value of every field with survivorship rules and records where it came from, keeps a crosswalk from every source id, and keeps history. New records are scored against the master with the saved model: 197 of 200 returning customers attached correctly. Uncertain ones go to a review queue, and every steward action is audited. GDPR erasure removes a person from every table."

## 10. Customer spine and hierarchy (17:00, 1 min)

**Slides:** 20.

**On screen:** slide 20, then `SELECT * FROM customer_spine WHERE household_size > 1`, the hierarchy query, and `spine_contracts.csv`.

**Say:** "The customer spine is the one table everybody joins to. Each row is a customer with its household, its source keys, the model version and the weakest link. Above it, a governed hierarchy: household, customer, source record, each edge with its rule and confidence. And governance is code: seven data contracts run on every build, and if one fails, nothing is published."

## 11. Identity drift (18:00, 1 min)

**Slides:** 21.

**On screen:** slide 21 (bar chart), `carry_forward()` in `07_identity_drift.py`.

**Say:** "Run the matching again next week and see what happens to the ids. Renumber the clusters and 56% of customers get a new id: every downstream table breaks. Carry the ids forward by overlap, keep the id for the largest part of a split, and keep an alias when two customers merge, and only 0.2% change."

## 12. MLOps: feature store, registry, monitoring (19:00, 1.25 min)

**Slides:** 22 (MLOps section), 23 (feature store, registry, promotion gate), 24 (monitoring without labels).

**On screen:** slides 22 and 23, then `FeatureStore` class, the registry and promotion lines, then slide 24 and `monitoring_report.csv`.

**Say:** "To run the ML matcher as a product, features live in a versioned feature store that training and scoring both read, so there is no skew. Models go into a registry; a challenger only becomes champion if it passes a gate on cluster quality and calibration. Then monitoring without labels: on a normal batch the score distribution is stable. On a broken feed, where phone numbers vanished and names became initials, four drift alerts fire, while the match rate on its own looks better. Watch more than one KPI."

## 13. From a laptop to a data platform (20:15, 1.25 min)

**Slides:** 25 (how it maps to a lakehouse), 26 (a reusable framework at scale).

**On screen:** slide 25, then slide 26. Optionally `databricks/splink_on_databricks.py`.

**Say:** "Everything so far runs on a laptop with DuckDB. On a data platform the shape is the same, only the backend changes. Bronze is one table per source, silver is the standardised customer table, then Splink on Spark with the graph repair and the review queue, and gold is the published layer: golden record, crosswalk, spine and hierarchy, with contracts and masks on personal data. New records arrive through change feeds and are matched incrementally. The Databricks notebook in the repository is a design example; I did not run it for this video.

If I had to build this for a real company, these are the eight steps [slide 26]. Start by asking how many records, which sources, batch or real time, and what a false merge costs. The last line is the important one: the matcher is configuration, so a new source is a config change, not a new project."

## 14. Summary (21:30, 1 min)

**Slides:** 27 (results by method), 28 (lessons), 29 (get the code).

**On screen:** slide 27, then 28, then 29 with the repository URL.

**Say:** "Here are all the numbers in one chart. Rules are explainable, Splink gives you learned weights without labels, ML gives you recall when you have labels, and graphs fix what pairs cannot see. Around that you need a master, a governed spine, stable ids and MLOps. Everything is in the repository, with a guide that explains every step. In production, expect messier data and lower numbers; the method is what carries over. The link is in the description: clone it, run it in under a minute, and tell me in the comments what your hardest matching problem is."

## B-roll and graphics list

- Three-system animation of one person's records (chapter 1).
- Blocking funnel: 33.5M → 6,405 pairs (chapter 3).
- Fellegi-Sunter weights adding up (chapter 5).
- Feature row for one pair, and the two-threshold bar (chapters 6 and 7).
- Chained cluster with a red min-cut edge, then the cut-by-cut Jones component (chapter 8).
- Bronze, silver and gold layers (chapter 13).
- Household → customer → source tree (chapter 10).
- Drift bar chart: 56% / 0.87% / 0.20% (chapter 11).
- Results table from `results/comparison.md` (chapter 14).
