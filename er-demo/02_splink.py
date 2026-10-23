"""Approach 2: probabilistic record linkage with Splink (Fellegi-Sunter, trained with EM, no labels).

Runs locally on DuckDB. On Databricks you swap DuckDBAPI for SparkAPI and nothing else changes
(see databricks/splink_on_databricks.py).
"""

import sys
from pathlib import Path

import logging

import pandas as pd
import splink.comparison_library as cl
from splink import DuckDBAPI, Linker, SettingsCreator, block_on

sys.path.insert(0, str(Path(__file__).parent))
from common.evaluate import evaluate_clusters  # noqa: E402
from common.standardise import standardise  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "results"
CLUSTER_THRESHOLD = 0.95

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
    blocking_rules_to_generate_predictions=[
        block_on("email"),
        block_on("phone"),
        block_on("dob", "surname_metaphone"),
        block_on("postcode", "first_metaphone"),
        block_on("first_name_canon", "last_name"),
    ],
    comparisons=[
        cl.NameComparison("first_name_canon").configure(
            term_frequency_adjustments=True
        ),
        cl.NameComparison("last_name").configure(term_frequency_adjustments=True),
        cl.DateOfBirthComparison("dob", input_is_string=True),
        cl.EmailComparison("email"),
        cl.ExactMatch("phone"),
        cl.PostcodeComparison("postcode"),
        cl.JaroWinklerAtThresholds("address", [0.95, 0.85]),
    ],
    retain_intermediate_calculation_columns=True,
)


def build_linker(df: pd.DataFrame):
    """Register standardized records in DuckDB and construct the Splink linker."""
    db_api = DuckDBAPI()
    sdf = db_api.register(df[MODEL_COLUMNS], table_name="customers")
    return Linker(sdf, settings, log_level=logging.WARNING), db_api


def train(linker: Linker):
    """Estimate the prior and u/m agreement parameters without labelled pairs."""
    # The prior estimates how rare a random match is, using these rules and an assumed
    # recall. It is distinct from the later per-pair evidence weights.
    linker.training.estimate_probability_two_random_records_match(
        [
            block_on("email"),
            block_on("phone"),
            block_on("first_name_canon", "last_name", "dob"),
        ],
        recall=0.7,
    )
    # u: how often different people agree at each comparison level, estimated from
    # random pairs where a true match is very unlikely.
    linker.training.estimate_u_using_random_sampling(max_pairs=2e6)
    # m: how often true matches agree at each level. EM uses likely matches in each
    # block; the blocking field itself cannot be learned in that run because it is fixed.
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("dob"))
    linker.training.estimate_parameters_using_expectation_maximisation(
        block_on("postcode")
    )
    linker.training.estimate_parameters_using_expectation_maximisation(
        block_on("first_name_canon", "last_name")
    )


def main():
    """Train Splink, score and cluster records, then save model, charts, and metrics."""
    OUT.mkdir(exist_ok=True)
    raw = pd.read_csv(HERE / "data/customers.csv")
    df = standardise(raw)
    linker, _ = build_linker(df)
    train(linker)

    # Keep predictions from p=0.2 onward so the review band and threshold sweep can
    # reuse one scored set instead of rerunning the model for every threshold.
    preds = linker.inference.predict(threshold_match_probability=0.2)
    # The selected threshold applies to pair probabilities before transitive clustering.
    clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(
        preds, CLUSTER_THRESHOLD
    )
    cdf = clusters.as_pandas_dataframe()
    metrics = evaluate_clusters(cdf.unique_id, cdf.cluster_id, cdf.true_entity_id)
    print("quality @", CLUSTER_THRESHOLD, metrics)

    # A threshold sweep shows how an operating choice changes cluster-level results;
    # these synthetic truth metrics are evaluation output, not production inputs.
    sweep = []
    for t in [0.5, 0.8, 0.9, 0.95, 0.99, 0.999]:
        c = linker.clustering.cluster_pairwise_predictions_at_threshold(
            preds, t
        ).as_pandas_dataframe()
        m = evaluate_clusters(c.unique_id, c.cluster_id, c.true_entity_id)
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
    print(sweep.to_string(index=False))

    # Save the fitted parameters as JSON so incremental jobs can score with this model
    # later without repeating unsupervised training.
    linker.misc.save_model_to_json(str(OUT / "splink_model.json"), overwrite=True)
    linker.visualisations.match_weights_chart().save(
        str(OUT / "splink_match_weights.html")
    )
    linker.visualisations.m_u_parameters_chart().save(
        str(OUT / "splink_m_u_parameters.html")
    )
    p = preds.as_pandas_dataframe()
    p[["unique_id_l", "unique_id_r", "match_weight", "match_probability"]].to_csv(
        OUT / "pairs_splink.csv", index=False
    )
    review = p[(p.match_probability >= 0.5) & (p.match_probability < CLUSTER_THRESHOLD)]
    review[["unique_id_l", "unique_id_r", "match_probability"]].to_csv(
        OUT / "review_queue_splink.csv", index=False
    )
    print(f"review queue (0.5 <= p < {CLUSTER_THRESHOLD}): {len(review)} pairs")
    # Select a representative scored pair and show how each comparison level adds to
    # or subtracts from its evidence. This makes the model's decision inspectable.
    rows = p.sort_values("match_probability").iloc[[len(p) // 3]].to_dict("records")
    linker.visualisations.waterfall_chart(rows, filter_nulls=False).save(
        str(OUT / "splink_waterfall_example.html")
    )
    cdf[["unique_id", "cluster_id"]].to_csv(OUT / "clusters_splink.csv", index=False)
    sweep.to_csv(OUT / "splink_threshold_sweep.csv", index=False)
    pd.DataFrame(
        [{"method": f"splink (EM, p>={CLUSTER_THRESHOLD})", **metrics}]
    ).to_csv(OUT / "metrics_splink.csv", index=False)


if __name__ == "__main__":
    main()
