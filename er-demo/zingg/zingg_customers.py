"""Approach 5: Zingg (ML entity resolution with active learning, runs on Spark).

NOT executed in the demo sandbox: Zingg needs Spark 3.5 + the Zingg jar (Docker image
`zingg/zingg` or the Databricks install). This script follows the Zingg Python API; check the
field/match-type names against the Zingg version you install.

How Zingg works (what to say in the interview):
  1. findTrainingData  -> Zingg picks the most informative uncertain pairs (active learning)
  2. label             -> a human marks them match / no match / not sure (CLI or Databricks UI)
  3. repeat 1-2 until ~30-40 positive pairs, then
  4. train             -> learns blocking functions AND a pairwise classifier from the labels
  5. match             -> output with z_cluster, z_minScore, z_maxScore per record
  6. link / runIncremental for linking two sources or new records against existing clusters

Inputs:
  /demo/data/customers.csv (the raw records, mounted into the container as /demo)

Outputs:
  /demo/zingg/models/customers_v1/   labelled pairs, learned blocking tree and classifier
  /demo/results/zingg_output/        CSV output of the match phase, one row per record

Run (Docker):
  docker run -it -v $PWD:/demo zingg/zingg:0.4.0 bash
  ./scripts/zingg.sh --run /demo/zingg/zingg_customers.py findTrainingData
  ./scripts/zingg.sh --run /demo/zingg/zingg_customers.py label
  ./scripts/zingg.sh --run /demo/zingg/zingg_customers.py train
  ./scripts/zingg.sh --run /demo/zingg/zingg_customers.py match

Slides: 8 (licence note under "Three ways to score a pair"), 12 (where labels come from).

Licence note: Zingg community is AGPL-3.0; enterprise version is commercial. Splink is MIT.
"""
import sys

# Zingg's Python client: Arguments holds the job configuration, FieldDefinition describes
# one input column, MatchType says how Zingg may compare it, Zingg runs a phase.
from zingg.client import Arguments, ClientOptions, FieldDefinition, MatchType, Zingg
# A "pipe" is Zingg's name for a data source or sink; CsvPipe reads or writes CSV files.
from zingg.pipes import CsvPipe

# The phase to run comes from the command line (see "Run" above); default is the first one.
PHASE = sys.argv[1] if len(sys.argv) > 1 else "findTrainingData"
# Mount point of the er-demo folder inside the Docker container.
BASE = "/demo"

# One FieldDefinition(column name, data type, match type) per input column, in file order.
# DONT_USE: carried through to the output but never compared.
# FUZZY: approximate string similarity. EXACT: must be equal. EMAIL: compares the part
# before the @. PINCODE: postcode-aware comparison. Zingg learns how much each field matters.
fields = [
    FieldDefinition("source_record_id", "string", MatchType.DONT_USE),
    FieldDefinition("source_system", "string", MatchType.DONT_USE),
    FieldDefinition("first_name", "string", MatchType.FUZZY),
    FieldDefinition("last_name", "string", MatchType.FUZZY),
    FieldDefinition("dob", "string", MatchType.EXACT),
    FieldDefinition("email", "string", MatchType.EMAIL),
    FieldDefinition("phone", "string", MatchType.EXACT),
    FieldDefinition("address", "string", MatchType.FUZZY),
    FieldDefinition("city", "string", MatchType.FUZZY),
    FieldDefinition("postcode", "string", MatchType.PINCODE),
    FieldDefinition("updated_at", "string", MatchType.DONT_USE),
    # The synthetic answer key is carried through for evaluation, never for matching.
    FieldDefinition("true_entity_id", "string", MatchType.DONT_USE),
]

# Job configuration shared by every phase.
args = Arguments()
args.setFieldDefinition(fields)
# The model id names the folder that holds the labels and the trained model, so every
# phase (findTrainingData, label, train, match) works on the same model.
args.setModelId("customers_v1")
args.setZinggDir(f"{BASE}/zingg/models")
# Number of Spark partitions: how many parallel chunks the data is split into.
args.setNumPartitions(4)
# Share of the data sampled when Zingg searches for uncertain pairs to show the labeller.
args.setLabelDataSampleSize(0.4)

# Spark schema string for the CSV columns, as "name type" pairs separated by commas.
schema = ("source_record_id string, source_system string, first_name string, last_name string, dob string, "
          "email string, phone string, address string, city string, postcode string, updated_at string, "
          "true_entity_id string")
# Input pipe: a name, the file path and the schema. The file has a header row.
inp = CsvPipe("customers", f"{BASE}/data/customers.csv", schema)
inp.setHeader("true")
args.setData(inp)
# Output pipe: where the match phase writes its CSV results.
args.setOutput(CsvPipe("customers_matched", f"{BASE}/results/zingg_output"))

# Build the client for the chosen phase and run it on Spark.
Zingg(args, ClientOptions([ClientOptions.PHASE, PHASE])).initAndExecute()

# After `match`: results/zingg_output has z_cluster per record. Evaluate with the same metrics:
#   from common.evaluate import evaluate_clusters
#   evaluate_clusters(out.source_record_id, out.z_cluster, out.true_entity_id)
