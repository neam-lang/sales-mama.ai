"""The board ranks only full rows of its own protocol version and prompt profile, never rows run with
exposed task IDs, and every view (table rank, vs leader, Pareto, cost index) uses the same rule.

    python tests/test_rank_eligibility.py      (from benchmark/space; needs pandas and numpy)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import src.load as load  # noqa: E402

LIVE = ("prospect", "recommend", "respond", "care")


def sub(sid: str, version: str, **bench) -> dict:
    return {"schema": "shl/v0.1", "id": sid, "date": "2026-11-25", "trials": 1,
            "harness": {"name": f"h-{sid}", "runtime": "test"}, "model": {"name": "m"},
            "benchmark": {"version": version, "split": "dev", **bench},
            "tracks": {k: {"score": 0.9, "n_tasks": 2} for k in LIVE},
            "per_task": [{"task": f"{k}-{i}", "track": k, "score": 0.9, "crit": 0, "trials": 1}
                         for k in LIVE for i in (1, 2)],
            "safety": {"runs": 8, "critical_violations": 0}, "efficiency": {"usd_per_task": 0.01}}


def ranks(subs: list) -> tuple[dict, dict, dict]:
    df = load.leaderboard_df(subs)
    return dict(zip(df["_id"], df["#"])), dict(zip(df["_id"], df["Status"])), dict(zip(df["_id"], df["_rankable"]))


def main() -> int:
    fails = []
    cur = load.BENCH_VERSION
    rank, status, ok = ranks([sub("a", cur), sub("b", cur, task_ids_exposed=True), sub("c", "SHB-SEA v9"),
                              sub("d", cur, prompt_profile="no-reminder")])
    if not (rank["a"] == "1" and rank["b"] == rank["c"] == rank["d"] == "—"):
        fails.append(f"ranks {rank}")
    if not ("task IDs exposed" in status["b"] and "this board ranks" in status["c"] and "prompt profile" in status["d"]):
        fails.append(f"status {status}")
    if ok != {"a": True, "b": False, "c": False, "d": False}:
        fails.append(f"_rankable {ok}")
    # When the board moves to a newer version, old rows stop ranking and the new ones rank.
    load.BENCH_VERSION = "SHB-SEA v0.1.2"
    rank, status, _ = ranks([
        sub("old", cur),
        sub("new", "SHB-SEA v0.1.2", prompt_profile="hinted", task_ids_exposed=False),
        sub("new-nr", "SHB-SEA v0.1.2", prompt_profile="no-reminder", task_ids_exposed=False),
        sub("new-no-exposure-field", "SHB-SEA v0.1.2", prompt_profile="hinted"),
        sub("new-no-profile", "SHB-SEA v0.1.2", task_ids_exposed=False)])
    load.BENCH_VERSION = cur
    if not (rank["new"] == "1" and all(rank[k] == "—" for k in ("old", "new-nr", "new-no-exposure-field",
                                                                  "new-no-profile"))):
        fails.append(f"newer version active: {rank}")
    if not ("not stated" in status["new-no-exposure-field"] and "not stated" in status["new-no-profile"]):
        fails.append(f"missing v0.1.2 metadata must be named: {status}")
    for name in ("index.html",):
        html = (HERE / "site" / name).read_text(encoding="utf-8")
        if "r._full && r[\"$/task\"]" in html or "D.rows.some((r) => r._full)" in html:
            fails.append(f"site/{name} still ranks or plots by _full")
    app = (HERE / "app.py").read_text(encoding="utf-8")
    if 'r["_full"] and pd.notna' in app or 'DF[DF["_full"]] if not DF.empty' in app:
        fails.append("app.py Pareto or cost index still uses _full")
    print("\n".join(fails) if fails else "rank eligibility OK (table, vs leader, Pareto and cost index)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
