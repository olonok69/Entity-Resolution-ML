# Databricks notebook source
# MAGIC %md
# MAGIC # Customer matching layer on Databricks (Splink + Delta + Unity Catalog + MLflow)
# MAGIC
# MAGIC Same model as `02_splink.py`, but on Spark. NOT executed in the demo sandbox (no workspace);
# MAGIC it shows how the local demo maps to the lakehouse:
# MAGIC
# MAGIC | Local demo | Databricks |
# MAGIC |---|---|
# MAGIC | CSV files | Bronze Delta tables per source (Lakeflow / Auto Loader) |
# MAGIC | `common/standardise.py` | Silver table `customer_std` (same functions as pandas UDFs or SQL) |
# MAGIC | DuckDBAPI | SparkAPI |
# MAGIC | results/*.csv | Delta tables in Unity Catalog: `pairs`, `clusters`, `golden_record`, `xref`, `review_queue` |
# MAGIC | splink_model.json | MLflow run artifact + registered model alias `champion` |
# MAGIC | 05_mdm.py incremental | Workflow task on Change Data Feed of the silver table |
# MAGIC
# MAGIC `%pip install splink` (cluster with Spark 3.4+; on serverless use the Splink Spark backend docs).

# COMMAND ----------
import mlflow
import splink.comparison_library as cl
from pyspark.sql import functions as F
from splink import Linker, SettingsCreator, SparkAPI, block_on

CATALOG, SCHEMA = "main", "customer_mdm"
spark.sql(f"USE {CATALOG}.{SCHEMA}")  # noqa: F821  (spark is provided by Databricks)
spark.sparkContext.setCheckpointDir(f"/Volumes/{CATALOG}/{SCHEMA}/checkpoints")  # noqa: F821

# Silver table produced by the standardisation job (one row per source record)
df = spark.table("customer_std")  # noqa: F821

# COMMAND ----------
# Splink settings mirror the laptop run; only the execution backend and table storage change.
settings = SettingsCreator(
    link_type="dedupe_only",
    unique_id_column_name="unique_id",
    blocking_rules_to_generate_predictions=[
        block_on("email"), block_on("phone"), block_on("dob", "surname_metaphone"),
        block_on("postcode", "first_metaphone"), block_on("first_name_canon", "last_name"),
    ],
    comparisons=[
        cl.NameComparison("first_name_canon").configure(term_frequency_adjustments=True),
        cl.NameComparison("last_name").configure(term_frequency_adjustments=True),
        cl.DateOfBirthComparison("dob", input_is_string=True),
        cl.EmailComparison("email"),
        cl.ExactMatch("phone"),
        cl.PostcodeComparison("postcode"),
        cl.JaroWinklerAtThresholds("address", [0.95, 0.85]),
    ],
)

db_api = SparkAPI(spark_session=spark, break_lineage_method="delta_lake_table")  # noqa: F821
linker = Linker(db_api.register(df), settings)

# COMMAND ----------
with mlflow.start_run(run_name="splink_customer_matching") as run:
    # Training uses comparison patterns only; no synthetic truth labels are supplied here.
    linker.training.estimate_probability_two_random_records_match(
        [block_on("email"), block_on("phone"), block_on("first_name_canon", "last_name", "dob")], recall=0.7)
    linker.training.estimate_u_using_random_sampling(max_pairs=5e7)
    for br in [block_on("dob"), block_on("postcode"), block_on("first_name_canon", "last_name")]:
        linker.training.estimate_parameters_using_expectation_maximisation(br)

    pairs = linker.inference.predict(threshold_match_probability=0.2)
    clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(pairs, 0.95)

    pairs_df = pairs.as_spark_dataframe()
    clusters_df = clusters.as_spark_dataframe()
    pairs_df.write.mode("overwrite").saveAsTable("pairs")
    clusters_df.write.mode("overwrite").saveAsTable("clusters")
    (pairs_df.filter((F.col("match_probability") >= 0.5) & (F.col("match_probability") < 0.95))
     .write.mode("overwrite").saveAsTable("review_queue"))

    linker.misc.save_model_to_json("/tmp/splink_model.json", overwrite=True)
    mlflow.log_artifact("/tmp/splink_model.json")
    mlflow.log_params({"cluster_threshold": 0.95, "review_band": "0.5-0.95"})

    # operational KPIs (no labels needed): watch these every run
    sizes = clusters_df.groupBy("cluster_id").count()
    mlflow.log_metrics({
        "n_records": clusters_df.count(),
        "n_entities": sizes.count(),
        "max_cluster_size": sizes.agg(F.max("count")).first()[0],
        "review_queue_size": spark.table("review_queue").count(),  # noqa: F821
    })
    # with a labelled golden set (steward decisions) also log pairwise / B-cubed precision & recall
    # using common/evaluate.py, and compare to the champion before promoting.

# COMMAND ----------
# MAGIC %md
# MAGIC Next tasks in the same Workflow (Databricks Asset Bundle):
# MAGIC 1. `golden_record` + `xref` with survivorship rules (port of `05_mdm.py`, set-based in Spark SQL)
# MAGIC 2. incremental: read Change Data Feed of `customer_std`, `linker.inference.predict_between(existing, new)`
# MAGIC 3. steward review app (Databricks Apps / Streamlit) writing decisions back to a Delta table = labels
# MAGIC 4. Unity Catalog column masks on PII columns, lineage for GDPR erasure
# MAGIC 5. optional: Mosaic AI Vector Search on name+address embeddings as an extra blocking rule for messy text
