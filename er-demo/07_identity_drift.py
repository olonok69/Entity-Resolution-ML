"""Step 7: identity drift. Do customer ids stay put when the matching runs again?

Identity drift is when the same real person gets a different customer id from one run to
the next, or when ids silently swap between people. Every downstream table keyed on the
id (orders, marketing consent, risk flags) then points at the wrong person.

This script runs the saved Splink model twice:
    run 1  the initial snapshot (data/customers.csv)
    run 2  a later snapshot: the same records, 5% of them with updated contact details,
           plus the new batch (data/new_batch.csv). Everything is re-clustered from scratch.

and compares three ways of assigning customer ids to run 2's clusters:
    sequential       number the clusters 1..n every run (what a naive rebuild does)
    representative   use a member record id as the cluster id (Splink's cluster_id)
    carry_forward    match run-2 clusters to run-1 ids by record overlap; on a split the
                     largest part keeps the id, on a merge the id with the larger overlap
                     survives (the older id on a tie) and the other gets an alias

Drift rate = share of run-1 records whose customer id changed. For context the report also
shows the share of records whose cluster really changed (somebody joined or left it). With
carry-forward only the records that split off or merged in get a new id; everyone else in a
changed cluster keeps theirs.

Inputs:
    data/customers.csv, data/new_batch.csv, results/splink_model.json

Outputs (in results/):
    identity_drift.csv   drift rate per id strategy, plus the membership-change context row
    id_alias.csv         retired_id -> surviving_id for every merge (old keys still resolve)
    id_events.csv        every carry-forward event: new, split, merged_into

How to run (from er-demo/):
    python 07_identity_drift.py

Run 02_splink.py first (it writes results/splink_model.json).

Slides: 21 (identity drift), 3 (56% -> 0.2% headline).
"""

import logging
# Python's own random module, seeded below, decides which contact field each update changes.
import random
import sys
from pathlib import Path

import pandas as pd
# DuckDBAPI runs Splink's SQL in an in-process DuckDB database; Linker is Splink's main object.
from splink import DuckDBAPI, Linker

# Put er-demo/ on the import path so "common" and "02_splink" can be imported.
sys.path.insert(0, str(Path(__file__).parent))
from common.standardise import standardise  # noqa: E402

# A module name that starts with a digit cannot be written in an import statement,
# so __import__ loads 02_splink.py by its string name. Its main() does not run on import.
splink_step = __import__("02_splink")  # reuse MODEL_COLUMNS

HERE = Path(__file__).parent
RES = HERE / "results"
# Same cluster threshold as 02_splink.py, so run 1 reproduces its 4,102 customers.
THRESHOLD = 0.95
# Share of records that get a changed phone or a dropped email in the later snapshot.
UPDATE_RATE = 0.05


def cluster(df: pd.DataFrame) -> pd.Series:
    """Score and cluster a snapshot with the saved model (no retraining). Returns cluster ids."""
    # A fresh DuckDB connection per run, so the two snapshots never share tables.
    db_api = DuckDBAPI()
    # Register only the columns the saved model expects, as a table named "snapshot".
    sdf = db_api.register(df[splink_step.MODEL_COLUMNS], table_name="snapshot")
    # Passing the JSON path loads the trained m / u parameters instead of training again.
    # Keeping the model fixed isolates drift caused by the data, not by a new model.
    linker = Linker(sdf, str(RES / "splink_model.json"), log_level=logging.WARNING)
    # Score the candidate pairs from the blocking rules, keeping pairs with p >= 0.5.
    preds = linker.inference.predict(threshold_match_probability=0.5)
    # Join pairs at p >= THRESHOLD into clusters by transitive closure (connected components).
    c = linker.clustering.cluster_pairwise_predictions_at_threshold(preds, THRESHOLD)
    # Splink's cluster_id is the id of one member record. Return it as a Series by unique_id.
    return c.as_pandas_dataframe().set_index("unique_id").cluster_id


def sequential(clusters: pd.Series) -> pd.Series:
    """Naive rebuild: number clusters in order of first appearance every run."""
    # Sort by record id, then pd.unique keeps the clusters in order of first appearance.
    # Enumerate them 1..n. Any new record early in the order shifts every later number.
    order = {c: i + 1 for i, c in enumerate(pd.unique(clusters.sort_index()))}
    # Format as "C0000001" style ids, the shape a warehouse key would have.
    return clusters.map(lambda c: f"C{order[c]:07d}")


def carry_forward(old_ids: pd.Series, new_clusters: pd.Series, next_seq: int):
    """Give run-2 clusters the run-1 id they overlap most; record merges and splits."""
    # One row per record in both runs: its run-1 customer id and its run-2 cluster.
    # dropna() removes new-batch records, which have no run-1 id.
    both = pd.DataFrame({"old": old_ids, "new": new_clusters}).dropna()
    # Overlap table: how many records each (new cluster, old id) combination shares.
    overlap = both.groupby(["new", "old"]).size().reset_index(name="n")
    # Process largest overlaps first so each old identity is retained by its largest
    # surviving piece. Lexical ordering makes equal-size ties deterministic.
    overlap = overlap.sort_values(["n", "old"], ascending=[False, True])
    # assigned: new cluster -> customer id. used: old ids already handed out.
    assigned, used = {}, set()
    for new, old, _ in overlap.itertuples(index=False):
        # Assign each prior ID to at most one new cluster, resolving splits by largest overlap.
        if new not in assigned and old not in used:
            assigned[new], used = old, used | {old}
    # Clusters still without an id get a fresh sequential one, and the reason is logged.
    events = []
    for new in pd.unique(new_clusters):
        if new not in assigned:
            assigned[new] = f"C{next_seq:07d}"
            next_seq += 1
            # Which old ids do this cluster's records come from?
            olds = both[both.new == new].old.unique()
            if len(olds):  # part of an old cluster that split off
                events.append({"event": "split", "id": assigned[new], "related_id": olds[0]})
            else:
                # Only new-batch records: a brand-new customer.
                events.append({"event": "new", "id": assigned[new], "related_id": None})
    # old ids that lost their cluster were merged into another one: keep an alias
    for old in sorted(set(old_ids.dropna()) - used):
        # A prior ID not retained by any cluster becomes an alias to its merge destination.
        # .mode()[0] picks the run-2 cluster holding most of that old id's records.
        target = assigned[both[both.old == old].new.mode()[0]]
        events.append({"event": "merged_into", "id": old, "related_id": target})
    # Map every record's run-2 cluster to its carried-forward customer id.
    return new_clusters.map(assigned), pd.DataFrame(events)


def drift(old: pd.Series, new: pd.Series) -> float:
    """Share of records present in both runs whose id changed."""
    # Records only in run 2 (the new batch) cannot drift, so compare the shared ones.
    common = old.index.intersection(new.index)
    # (a != b) is a boolean Series; its mean is the share of True values.
    return round(float((old.loc[common] != new.loc[common]).mean()), 4)


def membership_changed(old_c: pd.Series, new_c: pd.Series) -> float:
    """Context for drift: records whose set of run-1 co-members is different in run 2."""
    # Only run-1 records count. Restricting run 2 to them means a new-batch record
    # joining a cluster does not count as a change for the existing members.
    common = old_c.index
    # .groups maps each cluster label to the index (record ids) of its members.
    old_sets = old_c.groupby(old_c).groups
    new_r = new_c.loc[common]
    new_sets = new_r.groupby(new_r).groups
    # Compare membership sets, not raw cluster labels, since label values themselves
    # may change even when the actual group of records stays the same.
    # sum() over booleans counts the True values.
    changed = sum(
        set(old_sets[old_c[r]]) != set(new_sets[new_r[r]]) for r in common
    )
    return round(changed / len(common), 4)


def main():
    """Run the matcher on two snapshots and measure id drift for each id strategy."""
    raw = pd.read_csv(HERE / "data/customers.csv")
    batch = pd.read_csv(HERE / "data/new_batch.csv")

    # run 2 snapshot: some customers updated their phone or email, plus the new batch
    # Fixed seeds (7) make the same records change in the same way on every run.
    rng = random.Random(7)
    later = raw.copy()
    # sample(frac=0.05) picks 5% of rows at random; .index gives their row labels.
    upd = later.sample(frac=UPDATE_RATE, random_state=7).index
    for i in upd:
        # Half the updated records get a new random UK mobile number ("07" + 9 digits),
        # the other half lose their email. Both weaken the evidence that held clusters together.
        if rng.random() < 0.5:
            later.loc[i, "phone"] = "07" + "".join(rng.choice("0123456789") for _ in range(9))
        else:
            later.loc[i, "email"] = None
    # Append the new batch; ignore_index renumbers the rows 0..n-1.
    later = pd.concat([later, batch], ignore_index=True)

    # Cluster both snapshots from scratch with the same saved model.
    c1 = cluster(standardise(raw))
    c2 = cluster(standardise(later))
    print(f"run 1: {c1.nunique()} customers, run 2: {c2.nunique()} customers")

    run1_ids = sequential(c1)  # the ids published after run 1
    # Context row: share of run-1 records whose cluster membership really changed.
    floor = membership_changed(c1, c2)
    # Strategy 1, sequential: renumber run 2 from scratch.
    seq2 = sequential(c2)
    # Strategy 2, representative: use Splink's cluster_id (a member record id) as the key.
    # It only moves when that representative record ends up in another cluster.
    rep2 = c2.map(lambda c: f"R-{c}")
    rep1 = c1.map(lambda c: f"R-{c}")
    # Strategy 3, carry forward: new ids start after the last run-1 number.
    cf2, events = carry_forward(run1_ids, c2, next_seq=c1.nunique() + 1)

    rows = [
        # Sequential IDs expose renumbering; representative IDs anchor to one record;
        # carry-forward preserves IDs by overlap. The final row is a membership-change baseline.
        {"strategy": "sequential", "drift_rate": drift(run1_ids, seq2)},
        {"strategy": "representative", "drift_rate": drift(rep1, rep2)},
        {"strategy": "carry_forward", "drift_rate": drift(run1_ids, cf2)},
        {"strategy": "context: records whose cluster changed", "drift_rate": floor},
    ]
    report = pd.DataFrame(rows)
    print(report.to_string(index=False))
    # value_counts() counts each event type; to_dict() prints it as {"new": n, ...}.
    if len(events):
        print("carry-forward events:", events.event.value_counts().to_dict())

    # Write outputs. The alias table keeps only merges, with clearer column names, so a
    # downstream system can translate a retired id to the surviving one.
    RES.mkdir(exist_ok=True)
    report.to_csv(RES / "identity_drift.csv", index=False)
    events[events.event == "merged_into"].rename(
        columns={"id": "retired_id", "related_id": "surviving_id"}
    ).drop(columns="event").to_csv(RES / "id_alias.csv", index=False)
    events.to_csv(RES / "id_events.csv", index=False)


# Run main() only when the file is executed directly, not when it is imported.
if __name__ == "__main__":
    main()
