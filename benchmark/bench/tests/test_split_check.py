"""--split must match the selected tasks, and every task must state its split.

A test task under --split dev is refused, also when another track has a task with the same name; a task
without `split` is always refused (--expose-task-ids included).

    python tests/test_split_check.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import BENCH, make_task  # noqa: E402


def run(tasks: Path, out: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "shb.run", "--tasks", str(tasks), "--adapter", "null",
                           "--split", "dev", "--out", str(out), *extra], cwd=BENCH, capture_output=True, text=True)


def main() -> int:
    fails = []
    tmp = Path(tempfile.mkdtemp())
    make_task(tmp / "t1", "respond", "split-probe", {"grader": "checks", "checks": []})
    tj = tmp / "t1" / "dev" / "respond" / "split-probe" / "task.json"
    tj.write_text(tj.read_text(encoding="utf-8").replace('"split": "dev"', '"split": "test"'), encoding="utf-8")
    cp = run(tmp / "t1" / "dev", tmp / "o1.json")
    if not (cp.returncode == 2 and "not split 'dev'" in cp.stderr and not (tmp / "o1.json").exists()):
        fails.append(f"test task under --split dev must be refused: exit {cp.returncode} {cp.stderr[-200:]}")
    make_task(tmp / "t2", "respond", "no-split", {"grader": "checks", "checks": []})
    tj = tmp / "t2" / "dev" / "respond" / "no-split" / "task.json"
    t = json.loads(tj.read_text(encoding="utf-8")); t.pop("split"); tj.write_text(json.dumps(t), encoding="utf-8")
    cp = run(tmp / "t2" / "dev", tmp / "o2.json")
    if not (cp.returncode == 2 and "no `split`" in cp.stderr and not (tmp / "o2.json").exists()):
        fails.append(f"missing split must be refused: exit {cp.returncode} {cp.stderr[-200:]}")
    cp = run(tmp / "t2" / "dev", tmp / "o3.json", "--expose-task-ids")
    if not (cp.returncode == 2 and not (tmp / "o3.json").exists()):
        fails.append(f"missing split must be refused with --expose-task-ids too: exit {cp.returncode}")
    # Same task basename in two tracks: one dev, one test -> refused (checked per path, not per name).
    make_task(tmp / "t3", "respond", "same-name", {"grader": "checks", "checks": []})
    make_task(tmp / "t3", "care", "same-name", {"grader": "checks", "checks": []})
    tj = tmp / "t3" / "dev" / "care" / "same-name" / "task.json"
    tj.write_text(tj.read_text(encoding="utf-8").replace('"split": "dev"', '"split": "test"'), encoding="utf-8")
    cp = run(tmp / "t3" / "dev", tmp / "o4.json")
    if not (cp.returncode == 2 and "not split 'dev'" in cp.stderr):
        fails.append(f"same-basename mismatch must be refused: exit {cp.returncode} {cp.stderr[-200:]}")
    print("\n".join(fails) if fails else "split check OK: mismatch, same-name mismatch and missing split refused")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
