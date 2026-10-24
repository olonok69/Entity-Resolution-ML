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
"""Splink on Databricks: the 02_splink.py matcher, run on Spark with Delta and MLflow.

What it does:
    Trains the same Fellegi-Sunter model as 02_splink.py (same blocking rules, same
    comparisons, same training steps), but executes it on Spark through Splink's SparkAPI.
    Pairs, clusters and the review queue are written as Delta tables in Unity Catalog, and
    the model JSON, parameters and label-free KPIs are logged to an MLflow run.

Inputs:
    Unity Catalog table main.customer_mdm.customer_std (the Silver table: one standardised
    row per source record, with the columns that common/standardise.py creates).

Outputs (Delta tables in main.customer_mdm):
    pairs          every scored pair with p >= 0.2
    clusters       one row per record with its cluster_id (p >= 0.95)
    review_queue   pairs in the grey zone 0.5 <= p < 0.95, for data stewards
    plus an MLflow run with splink_model.json, params and KPIs.

How to run:
    Import into a Databricks workspace as a notebook and run it on a cluster with
    Spark 3.4+ and Splink installed. NOT executed in this demo: there is no workspace here,
    and the variable `spark` only exists inside Databricks.

File format: this is a Databricks notebook exported as source. Lines starting with
"# MAGIC %md" render as Markdown cells and "# COMMAND ----------" separates cells.
To plain Python both are comments, so this docstring is still the module docstring.

Slides: 25 (lakehouse mapping), 26 (framework at scale), 23 (MLflow registry and gate).
"""
# mlflow tracks runs: parameters, metrics and files ("artifacts") per training run.
import mlflow
# Splink's ready-made comparison templates (name, DOB, email, postcode, ...).
import splink.comparison_library as cl
# Spark column functions: F.col("x") refers to a column, F.max aggregates, and so on.
from pyspark.sql import functions as F
# SparkAPI is the Spark backend, the drop-in replacement for DuckDBAPI used locally.
from splink import Linker, SettingsCreator, SparkAPI, block_on

# Unity Catalog uses a three-level name: catalog.schema.table.
CATALOG, SCHEMA = "main", "customer_mdm"
# Make main.customer_mdm the default, so tables below can be named without a prefix.
spark.sql(f"USE {CATALOG}.{SCHEMA}")  # noqa: F821  (spark is provided by Databricks)
# Splink's iterative Spark jobs build very long query plans. Checkpointing to a Unity
# Catalog volume lets Spark cut that lineage and keep jobs fast and stable.
spark.sparkContext.setCheckpointDir(f"/Volumes/{CATALOG}/{SCHEMA}/checkpoints")  # noqa: F821

# Silver table produced by the standardisation job (one row per source record)
df = spark.table("customer_std")  # noqa: F821

# COMMAND ----------
# Splink settings mirror the laptop run; only the execution backend and table storage change.
settings = SettingsCreator(
    # One combined table of all sources, so look for duplicates inside it.
    link_type="dedupe_only",
    unique_id_column_name="unique_id",
    # Blocking: only pairs that agree exactly on at least one of these keys are scored.
    # This avoids comparing every record with every other record (n squared pairs).
    blocking_rules_to_generate_predictions=[
        block_on("email"), block_on("phone"), block_on("dob", "surname_metaphone"),
        block_on("postcode", "first_metaphone"), block_on("first_name_canon", "last_name"),
    ],
    # Comparisons: each field gets levels (exact, fuzzy, different) with learned m and u.
    # Term-frequency adjustment gives a rare surname more weight than "smith".
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

# break_lineage_method="delta_lake_table" makes Splink write intermediate results to
# Delta tables instead of keeping one huge in-memory Spark plan.
db_api = SparkAPI(spark_session=spark, break_lineage_method="delta_lake_table")  # noqa: F821
# Register the Silver DataFrame with the backend and build the linker from the settings.
linker = Linker(db_api.register(df), settings)

# COMMAND ----------
# Everything inside this block is recorded in one MLflow run.
with mlflow.start_run(run_name="splink_customer_matching") as run:
    # Training uses comparison patterns only; no synthetic truth labels are supplied here.
    # Step 1, the prior: estimate how likely two random records are the same person, from
    # pairs these deterministic rules find, assuming the rules catch 70% of true matches.
    linker.training.estimate_probability_two_random_records_match(
        [block_on("email"), block_on("phone"), block_on("first_name_canon", "last_name", "dob")], recall=0.7)
    # Step 2, u values: how often different people agree on each level by chance, from a
    # random sample of pairs (almost all non-matches). 5e7 pairs, larger than the local 2e6.
    linker.training.estimate_u_using_random_sampling(max_pairs=5e7)
    # Step 3, m values: expectation maximisation inside each block. A field used in the
    # block cannot be learned in that pass, so three different blocks cover all fields.
    for br in [block_on("dob"), block_on("postcode"), block_on("first_name_canon", "last_name")]:
        linker.training.estimate_parameters_using_expectation_maximisation(br)

    # Score candidate pairs (keep p >= 0.2 so the review band can be cut from one table),
    # then cluster pairs at p >= 0.95 into customers by connected components.
    pairs = linker.inference.predict(threshold_match_probability=0.2)
    clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(pairs, 0.95)

    # Convert Splink results to Spark DataFrames and save them as managed Delta tables.
    pairs_df = pairs.as_spark_dataframe()
    clusters_df = clusters.as_spark_dataframe()
    pairs_df.write.mode("overwrite").saveAsTable("pairs")
    clusters_df.write.mode("overwrite").saveAsTable("clusters")
    # The grey zone: likely but not certain matches go to a human steward.
    (pairs_df.filter((F.col("match_probability") >= 0.5) & (F.col("match_probability") < 0.95))
     .write.mode("overwrite").saveAsTable("review_queue"))

    # Save the trained m / u parameters and attach the JSON file to the MLflow run, so the
    # exact model behind these tables can be reloaded and audited later.
    linker.misc.save_model_to_json("/tmp/splink_model.json", overwrite=True)
    mlflow.log_artifact("/tmp/splink_model.json")
    mlflow.log_params({"cluster_threshold": 0.95, "review_band": "0.5-0.95"})

    # operational KPIs (no labels needed): watch these every run
    # Records per cluster: a sudden jump in max_cluster_size is the classic chaining alarm.
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
