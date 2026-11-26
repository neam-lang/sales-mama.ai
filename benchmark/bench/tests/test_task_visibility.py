"""The harness under test must not see answer-bearing task IDs.

Respond IDs end with the gold class (respond-01-en-unsubscribe), Care IDs carry
pos/neg and Guard IDs name the trap. A harness that reads only TASK.md's title
or SHB_TASK_ID could otherwise score without doing the task.

    python tests/test_task_visibility.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import make_task, run_bench, write_adapter  # noqa: E402

LEAKY = {"respond": "respond-99-en-unsubscribe", "care": "care-neg_en_9999", "guard": "guard-99-injected-news"}
OBSERVER = '''import json, os, sys
from pathlib import Path
box = Path(sys.argv[1])
(box / "answer.json").write_text(json.dumps({
    "task_md": (box / "TASK.md").read_text(encoding="utf-8"),
    "env_task_id": os.environ.get("SHB_TASK_ID", "")}), encoding="utf-8")
'''
WORDS = ("unsubscribe", "neg", "injected", "news", "respond-99", "care-neg", "guard-99")


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    for track, tid in LEAKY.items():
        make_task(tmp / "tasks", track, tid, {"grader": "checks", "checks": []})
    adapter = write_adapter(tmp / "observer.py", OBSERVER)
    keep = tmp / "traces"
    # An ambient override in the caller's environment must not re-expose real IDs.
    import os
    env = {**os.environ, "SHB_EXPOSE_TASK_ID": "1"}
    res = run_bench(tmp / "tasks", adapter, "--keep-traces", str(keep), "--trials", "2", env=env)
    fails = []
    handles = {}
    for track, tid in LEAKY.items():
        seen = json.loads((keep / tid / "trial1" / "answer.json").read_text(encoding="utf-8"))
        again = json.loads((keep / tid / "trial2" / "answer.json").read_text(encoding="utf-8"))
        h = seen["env_task_id"]
        if not h or h not in seen["task_md"].splitlines()[0]:
            fails.append(f"{tid}: handle missing or not the one shown in TASK.md ({h!r})")
        if again["env_task_id"] != h:
            fails.append(f"{tid}: handle must be stable across trials of one campaign")
        handles[tid] = h
        title = seen["task_md"].splitlines()[0]
        for blob, where in ((title, "TASK.md title"), (seen["env_task_id"], "SHB_TASK_ID")):
            hit = [w for w in WORDS if w in blob.lower()]
            if hit:
                fails.append(f"{tid}: {where} exposes {hit}: {blob!r}")
    if len(set(handles.values())) != len(handles):
        fails.append(f"handles must differ across tasks: {handles}")
    ids = sorted(p["task"] for p in res["per_task"])
    if ids != sorted(LEAKY.values()):
        fails.append(f"result IDs must stay stable for scoring, got {ids}")
    print("\n".join(fails) if fails else "task visibility OK: agent sees opaque handles, results keep real IDs")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
