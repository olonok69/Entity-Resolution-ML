"""Approach 2: probabilistic record linkage with Splink (Fellegi-Sunter, trained with EM, no labels).

Runs locally on DuckDB. On Databricks you swap DuckDBAPI for SparkAPI and nothing else changes
(see databricks/splink_on_databricks.py).

How it works (DEMO_GUIDE.md section 3.5):
  - Each field (name, DOB, email, ...) is compared on a ladder of comparison levels
    (exact, small typo, ..., all other). Every pair lands on exactly one level per field.
  - m = P(level | the two records are the same person); u = P(level | different people).
  - Each level adds log2(m / u) bits of evidence. The prior (how rare a random match is)
    is the starting value. The total converts to a match probability.
  - u is learned from random pairs, m with expectation-maximisation (EM). No labels.

Input:  data/customers.csv
Output: results/splink_model.json            trained model, reused by 05, 06 and 07
        results/pairs_splink.csv             scored pairs (match_weight, match_probability), used by 04
        results/clusters_splink.csv          record -> cluster at CLUSTER_THRESHOLD
        results/review_queue_splink.csv      pairs with 0.5 <= p < CLUSTER_THRESHOLD
        results/splink_threshold_sweep.csv   cluster metrics at several thresholds
        results/splink_match_weights.html, splink_m_u_parameters.html,
        splink_waterfall_example.html        model charts
        results/metrics_splink.csv           one row of quality metrics
Run:    python 02_splink.py   (from the er-demo folder)
Slides: 7 (blocking), 8 (three ways to score), 9 (fields, levels, m and u),
        10 (adding up bits), 13 (precision or recall).

Expected console warnings: Splink prints "not observed in dataset, unable to train m value"
for the DOB "Levenshtein distance <= 1" level and the postcode "sector" and "district"
levels, then a "m values not fully trained" warning at predict(). The synthetic data never
produces those patterns for true matches (DOB errors are day-month swaps, and people who
move get a completely new postcode), so EM has nothing to learn from and Splink uses
default m values for those few levels. This is expected and harmless here.
"""

# sys and Path let the script find the shared "common" package next to it.
import sys
from pathlib import Path

# logging.WARNING is passed to the Linker to keep Splink's console output short.
import logging

import pandas as pd

# comparison_library (cl) holds ready-made comparisons, each a ladder of levels.
import splink.comparison_library as cl

# DuckDBAPI: run Splink's SQL on a local in-memory DuckDB database.
# Linker: the main Splink object (training, prediction, clustering, charts).
# SettingsCreator: the model specification. block_on: builds a blocking rule.
from splink import DuckDBAPI, Linker, SettingsCreator, block_on

# Make "common" importable no matter which folder the script is started from.
sys.path.insert(0, str(Path(__file__).parent))
from common.evaluate import evaluate_clusters  # noqa: E402
from common.standardise import standardise  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "results"
# Pairs with match probability >= 0.95 become edges for clustering.
CLUSTER_THRESHOLD = 0.95

# Columns sent to DuckDB. Splink only needs the ID, the compared fields and the
# blocking keys; the rest are carried along for inspection and evaluation.
MODEL_COLUMNS = [
    "unique_id",
    "source_system",
    "first_name",
    "first_name_canon",
    "last_name",
    "dob",
    "email",
    "phone",
    "postcode",
    "postcode_area",
    "address",
    "surname_metaphone",
    "first_metaphone",
    "updated_at",
    # Retained for evaluation only; it is not used by the blocking rules or comparisons.
    "true_entity_id",
]

# Blocking determines which pairs Splink scores; comparisons describe the evidence
# it measures for those pairs. Dedupe-only is appropriate because all source systems
# have already been combined into one standardized table.
settings = SettingsCreator(
    link_type="dedupe_only",  # all sources in one table; use "link_and_dedupe" with a list of tables
    unique_id_column_name="unique_id",
    # The same five blocking keys as 01_rules_rapidfuzz.py (Splink takes the union of
    # the rules, without step 1's cap on blocks over 200 records).
    blocking_rules_to_generate_predictions=[
        block_on("email"),
        block_on("phone"),
        block_on("dob", "surname_metaphone"),
        block_on("postcode", "first_metaphone"),
        block_on("first_name_canon", "last_name"),
    ],
    # The seven fields of slide 9. Each comparison is a ladder of levels checked top
    # to bottom; the pair lands on the first level that is true. Every level later
    # gets its own m and u, and therefore its own weight log2(m / u).
    comparisons=[
        # Name ladder: exact, Jaro-Winkler >= 0.92, >= 0.88, >= 0.70, all other.
        # Term-frequency adjustment: agreeing on a rare name earns more bits than
        # agreeing on a common one such as "smith".
        cl.NameComparison("first_name_canon").configure(
            term_frequency_adjustments=True
        ),
        cl.NameComparison("last_name").configure(term_frequency_adjustments=True),
        # DOB ladder: exact, Levenshtein <= 1, within 1 month, 1 year, 10 years, all other.
        # input_is_string=True: the column holds "YYYY-MM-DD" text, not a date type.
        cl.DateOfBirthComparison("dob", input_is_string=True),
        # Email ladder: exact, same username, fuzzy email, fuzzy username, all other.
        cl.EmailComparison("email"),
        # Phone: exact or not; partial phone agreement is not useful evidence.
        cl.ExactMatch("phone"),
        # UK postcode ladder: full, sector (WR3 3), district (WR3), area (WR), all other.
        cl.PostcodeComparison("postcode"),
        # Address: exact, Jaro-Winkler >= 0.95, >= 0.85, all other.
        cl.JaroWinklerAtThresholds("address", [0.95, 0.85]),
    ],
    # Keep per-field levels and weights in the predictions, needed for the waterfall chart.
    retain_intermediate_calculation_columns=True,
)


def build_linker(df: pd.DataFrame):
    """Register standardized records in DuckDB and construct the Splink linker."""
    # An in-memory DuckDB database; Splink writes all its work as SQL against it.
    db_api = DuckDBAPI()
    # Load the selected columns as a DuckDB table named "customers".
    sdf = db_api.register(df[MODEL_COLUMNS], table_name="customers")
    # The Linker ties data, settings and backend together. Returning db_api too keeps
    # the database reachable for callers that need it.
    return Linker(sdf, settings, log_level=logging.WARNING), db_api


def train(linker: Linker):
    """Estimate the prior and u/m agreement parameters without labelled pairs."""
    # 1) The prior (lambda), the starting point of every pair's score (slide 10).
    # The prior estimates how rare a random match is, using these rules and an assumed
    # recall. It is distinct from the later per-pair evidence weights.
    # Splink counts pairs that pass these strict rules, assumes they find 70% of all
    # true matches (recall=0.7), and divides by the number of possible pairs.
    # Here lambda is about 0.00022, which is -12.1 bits.
    linker.training.estimate_probability_two_random_records_match(
        [
            block_on("email"),
            block_on("phone"),
            block_on("first_name_canon", "last_name", "dob"),
        ],
        recall=0.7,
    )
    # 2) u for every level (slide 9).
    # u: how often different people agree at each comparison level, estimated from
    # random pairs where a true match is very unlikely.
    # Up to 2 million random pairs are sampled; the share landing on each level is u.
    linker.training.estimate_u_using_random_sampling(max_pairs=2e6)
    # 3) m for every level, with expectation-maximisation (EM), in three sessions.
    # m: how often true matches agree at each level. EM uses likely matches in each
    # block; the blocking field itself cannot be learned in that run because it is fixed.
    # Each session: guess m, score the pairs in the block, recompute m weighting each
    # pair by its match probability, and repeat until the values stop changing.
    # Session 1 blocks on DOB, so every pair agrees on DOB: it learns m for all fields
    # except DOB. Postcode "sector" and "district" may print "not observed" here.
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("dob"))
    # Session 2 blocks on postcode: it learns DOB (and the rest) but not postcode.
    # DOB "Levenshtein distance <= 1" may print "not observed" here.
    linker.training.estimate_parameters_using_expectation_maximisation(
        block_on("postcode")
    )
    # Session 3 blocks on full name: it learns DOB, postcode, email, phone and address
    # but not the names. Splink averages each field's m over the sessions that could
    # learn it, so every field is learned at least once.
    linker.training.estimate_parameters_using_expectation_maximisation(
        block_on("first_name_canon", "last_name")
    )


def main():
    """Train Splink, score and cluster records, then save model, charts, and metrics."""
    OUT.mkdir(exist_ok=True)
    # Load and clean the same records as approach 1.
    raw = pd.read_csv(HERE / "data/customers.csv")
    df = standardise(raw)
    # The second return value (db_api) is not needed here.
    linker, _ = build_linker(df)
    # Unsupervised training: true_entity_id is never used.
    train(linker)

    # Score every candidate pair: total weight = prior + sum of level weights, then
    # probability = 2^w / (1 + 2^w). Splink prints the "m values not fully trained"
    # warning here for the untrained DOB and postcode levels.
    # Keep predictions from p=0.2 onward so the review band and threshold sweep can
    # reuse one scored set instead of rerunning the model for every threshold.
    preds = linker.inference.predict(threshold_match_probability=0.2)
    # Keep pairs with p >= 0.95 as edges and take connected components.
    # The selected threshold applies to pair probabilities before transitive clustering.
    clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(
        preds, CLUSTER_THRESHOLD
    )
    # Bring the DuckDB result back as a pandas DataFrame (unique_id, cluster_id, ...).
    cdf = clusters.as_pandas_dataframe()
    # Compare with the synthetic truth, exactly as approach 1 does.
    metrics = evaluate_clusters(cdf.unique_id, cdf.cluster_id, cdf.true_entity_id)
    print("quality @", CLUSTER_THRESHOLD, metrics)

    # A threshold sweep shows how an operating choice changes cluster-level results;
    # these synthetic truth metrics are evaluation output, not production inputs.
    # Higher thresholds give fewer edges: precision goes up, recall goes down (slide 13).
    sweep = []
    for t in [0.5, 0.8, 0.9, 0.95, 0.99, 0.999]:
        # Re-cluster the same scored pairs at threshold t; no retraining needed.
        c = linker.clustering.cluster_pairwise_predictions_at_threshold(
            preds, t
        ).as_pandas_dataframe()
        m = evaluate_clusters(c.unique_id, c.cluster_id, c.true_entity_id)
        # Keep the threshold plus a few headline metrics for the table.
        sweep.append(
            {
                "threshold": t,
                **{
                    k: m[k]
                    for k in [
                        "pair_precision",
                        "pair_recall",
                        "pair_f1",
                        "bcubed_f1",
                        "n_pred_entities",
                    ]
                },
            }
        )
    sweep = pd.DataFrame(sweep)
    # to_string(index=False) prints the table without the pandas row numbers.
    print(sweep.to_string(index=False))

    # Save the fitted parameters as JSON so incremental jobs can score with this model
    # later without repeating unsupervised training.
    # The JSON holds the settings, the prior, and m and u for every level.
    linker.misc.save_model_to_json(str(OUT / "splink_model.json"), overwrite=True)
    # Chart of log2(m / u) per level: the "bits" of slides 9 and 10.
    linker.visualisations.match_weights_chart().save(
        str(OUT / "splink_match_weights.html")
    )
    # Chart of the raw m and u per level, side by side.
    linker.visualisations.m_u_parameters_chart().save(
        str(OUT / "splink_m_u_parameters.html")
    )
    # All scored pairs (p >= 0.2) with weight and probability; 04_graph_resolution.py
    # uses them as weighted graph edges.
    p = preds.as_pandas_dataframe()
    p[["unique_id_l", "unique_id_r", "match_weight", "match_probability"]].to_csv(
        OUT / "pairs_splink.csv", index=False
    )
    # Grey zone: likely matches that are not sure enough to merge automatically.
    review = p[(p.match_probability >= 0.5) & (p.match_probability < CLUSTER_THRESHOLD)]
    review[["unique_id_l", "unique_id_r", "match_probability"]].to_csv(
        OUT / "review_queue_splink.csv", index=False
    )
    print(f"review queue (0.5 <= p < {CLUSTER_THRESHOLD}): {len(review)} pairs")
    # Select a representative scored pair and show how each comparison level adds to
    # or subtracts from its evidence. This makes the model's decision inspectable.
    # Sort by probability and pick the pair one third of the way up the list.
    rows = p.sort_values("match_probability").iloc[[len(p) // 3]].to_dict("records")
    # Waterfall: prior bar, then one bar per field, ending at the final weight (slide 10).
    # filter_nulls=False also shows fields that were missing (weight 0).
    linker.visualisations.waterfall_chart(rows, filter_nulls=False).save(
        str(OUT / "splink_waterfall_example.html")
    )
    # Record-to-cluster assignment at CLUSTER_THRESHOLD.
    cdf[["unique_id", "cluster_id"]].to_csv(OUT / "clusters_splink.csv", index=False)
    sweep.to_csv(OUT / "splink_threshold_sweep.csv", index=False)
    # One metrics row tagged with the method name for 09_compare.py.
    pd.DataFrame(
        [{"method": f"splink (EM, p>={CLUSTER_THRESHOLD})", **metrics}]
    ).to_csv(OUT / "metrics_splink.csv", index=False)


if __name__ == "__main__":
    main()
