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
                     largest part keeps the id, on a merge the older id survives and the
                     other is retired with an alias, so old keys still resolve

Drift rate = share of run-1 records whose customer id changed. For context the report also
shows the share of records whose cluster really changed (somebody joined or left it). With
carry-forward only the records that split off or merged in get a new id; everyone else in a
changed cluster keeps theirs.

Run 02_splink.py first (it writes results/splink_model.json).
"""

import logging
import random
import sys
from pathlib import Path

import pandas as pd
from splink import DuckDBAPI, Linker

sys.path.insert(0, str(Path(__file__).parent))
from common.standardise import standardise  # noqa: E402

splink_step = __import__("02_splink")  # reuse MODEL_COLUMNS

HERE = Path(__file__).parent
RES = HERE / "results"
THRESHOLD = 0.95
UPDATE_RATE = 0.05


def cluster(df: pd.DataFrame) -> pd.Series:
    """Score and cluster a snapshot with the saved model (no retraining). Returns cluster ids."""
    db_api = DuckDBAPI()
    sdf = db_api.register(df[splink_step.MODEL_COLUMNS], table_name="snapshot")
    linker = Linker(sdf, str(RES / "splink_model.json"), log_level=logging.WARNING)
    preds = linker.inference.predict(threshold_match_probability=0.5)
    c = linker.clustering.cluster_pairwise_predictions_at_threshold(preds, THRESHOLD)
    return c.as_pandas_dataframe().set_index("unique_id").cluster_id


def sequential(clusters: pd.Series) -> pd.Series:
    """Naive rebuild: number clusters in order of first appearance every run."""
    order = {c: i + 1 for i, c in enumerate(pd.unique(clusters.sort_index()))}
    return clusters.map(lambda c: f"C{order[c]:07d}")


def carry_forward(old_ids: pd.Series, new_clusters: pd.Series, next_seq: int):
    """Give run-2 clusters the run-1 id they overlap most; record merges and splits."""
    both = pd.DataFrame({"old": old_ids, "new": new_clusters}).dropna()
    overlap = both.groupby(["new", "old"]).size().reset_index(name="n")
    # Process largest overlaps first so each old identity is retained by its largest
    # surviving piece. Lexical ordering makes equal-size ties deterministic.
    overlap = overlap.sort_values(["n", "old"], ascending=[False, True])
    assigned, used = {}, set()
    for new, old, _ in overlap.itertuples(index=False):
        # Assign each prior ID to at most one new cluster, resolving splits by largest overlap.
        if new not in assigned and old not in used:
            assigned[new], used = old, used | {old}
    events = []
    for new in pd.unique(new_clusters):
        if new not in assigned:
            assigned[new] = f"C{next_seq:07d}"
            next_seq += 1
            olds = both[both.new == new].old.unique()
            if len(olds):  # part of an old cluster that split off
                events.append({"event": "split", "id": assigned[new], "related_id": olds[0]})
            else:
                events.append({"event": "new", "id": assigned[new], "related_id": None})
    # old ids that lost their cluster were merged into another one: keep an alias
    for old in sorted(set(old_ids.dropna()) - used):
        # A prior ID not retained by any cluster becomes an alias to its merge destination.
        target = assigned[both[both.old == old].new.mode()[0]]
        events.append({"event": "merged_into", "id": old, "related_id": target})
    return new_clusters.map(assigned), pd.DataFrame(events)


def drift(old: pd.Series, new: pd.Series) -> float:
    """Share of records present in both runs whose id changed."""
    common = old.index.intersection(new.index)
    return round(float((old.loc[common] != new.loc[common]).mean()), 4)


def membership_changed(old_c: pd.Series, new_c: pd.Series) -> float:
    """Context for drift: records whose set of run-1 co-members is different in run 2."""
    common = old_c.index
    old_sets = old_c.groupby(old_c).groups
    new_r = new_c.loc[common]
    new_sets = new_r.groupby(new_r).groups
    # Compare membership sets, not raw cluster labels, since label values themselves
    # may change even when the actual group of records stays the same.
    changed = sum(
        set(old_sets[old_c[r]]) != set(new_sets[new_r[r]]) for r in common
    )
    return round(changed / len(common), 4)


def main():
    """Run the matcher on two snapshots and measure id drift for each id strategy."""
    raw = pd.read_csv(HERE / "data/customers.csv")
    batch = pd.read_csv(HERE / "data/new_batch.csv")

    # run 2 snapshot: some customers updated their phone or email, plus the new batch
    rng = random.Random(7)
    later = raw.copy()
    upd = later.sample(frac=UPDATE_RATE, random_state=7).index
    for i in upd:
        if rng.random() < 0.5:
            later.loc[i, "phone"] = "07" + "".join(rng.choice("0123456789") for _ in range(9))
        else:
            later.loc[i, "email"] = None
    later = pd.concat([later, batch], ignore_index=True)

    c1 = cluster(standardise(raw))
    c2 = cluster(standardise(later))
    print(f"run 1: {c1.nunique()} customers, run 2: {c2.nunique()} customers")

    run1_ids = sequential(c1)  # the ids published after run 1
    floor = membership_changed(c1, c2)
    seq2 = sequential(c2)
    rep2 = c2.map(lambda c: f"R-{c}")
    rep1 = c1.map(lambda c: f"R-{c}")
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
    if len(events):
        print("carry-forward events:", events.event.value_counts().to_dict())

    RES.mkdir(exist_ok=True)
    report.to_csv(RES / "identity_drift.csv", index=False)
    events[events.event == "merged_into"].rename(
        columns={"id": "retired_id", "related_id": "surviving_id"}
    ).drop(columns="event").to_csv(RES / "id_alias.csv", index=False)
    events.to_csv(RES / "id_events.csv", index=False)


if __name__ == "__main__":
    main()
