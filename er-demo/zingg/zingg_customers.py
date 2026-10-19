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

Run (Docker):
  docker run -it -v $PWD:/demo zingg/zingg:0.4.0 bash
  ./scripts/zingg.sh --run /demo/zingg/zingg_customers.py findTrainingData
  ./scripts/zingg.sh --run /demo/zingg/zingg_customers.py label
  ./scripts/zingg.sh --run /demo/zingg/zingg_customers.py train
  ./scripts/zingg.sh --run /demo/zingg/zingg_customers.py match

Licence note: Zingg community is AGPL-3.0; enterprise version is commercial. Splink is MIT.
"""
import sys

from zingg.client import Arguments, ClientOptions, FieldDefinition, MatchType, Zingg
from zingg.pipes import CsvPipe

PHASE = sys.argv[1] if len(sys.argv) > 1 else "findTrainingData"
BASE = "/demo"

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
    FieldDefinition("true_entity_id", "string", MatchType.DONT_USE),  # evaluation only
]

args = Arguments()
args.setFieldDefinition(fields)
args.setModelId("customers_v1")
args.setZinggDir(f"{BASE}/zingg/models")
args.setNumPartitions(4)
args.setLabelDataSampleSize(0.4)

schema = ("source_record_id string, source_system string, first_name string, last_name string, dob string, "
          "email string, phone string, address string, city string, postcode string, updated_at string, "
          "true_entity_id string")
inp = CsvPipe("customers", f"{BASE}/data/customers.csv", schema)
inp.setHeader("true")
args.setData(inp)
args.setOutput(CsvPipe("customers_matched", f"{BASE}/results/zingg_output"))

Zingg(args, ClientOptions([ClientOptions.PHASE, PHASE])).initAndExecute()

# After `match`: results/zingg_output has z_cluster per record. Evaluate with the same metrics:
#   from common.evaluate import evaluate_clusters
#   evaluate_clusters(out.source_record_id, out.z_cluster, out.true_entity_id)
