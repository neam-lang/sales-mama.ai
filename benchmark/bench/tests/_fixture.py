"""Tiny synthetic task worlds for runner tests (stdlib only, no real tasks needed)."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent


def make_task(root: Path, track: str, task_id: str, gold: dict, time_limit_s: int = 60) -> None:
    d = root / "dev" / track / task_id
    (d / "world").mkdir(parents=True)
    (d / "world" / "README.md").write_text("fixture world\n", encoding="utf-8")
    task = {"id": task_id, "track": track, "split": "dev", "instruction": "Write answer.json.",
            "answer_schema": {"ok": "yes|no"}, "time_limit_s": time_limit_s}
    (d / "task.json").write_text(json.dumps(task), encoding="utf-8")
    (d / "gold.json").write_text(json.dumps(gold), encoding="utf-8")


def write_adapter(path: Path, body: str) -> str:
    path.write_text(body, encoding="utf-8")
    return f'"{sys.executable}" "{path}"'


def run_bench(tasks_root: Path, adapter: str, *extra: str, env: dict | None = None) -> dict:
    out = Path(tempfile.mkdtemp()) / "out.json"
    cmd = [sys.executable, "-m", "shb.run", "--tasks", str(tasks_root / "dev"), "--adapter", adapter,
           "--out", str(out), *extra]
    subprocess.run(cmd, cwd=BENCH, check=True, capture_output=True, env=env)
    return json.loads(out.read_text(encoding="utf-8"))
