"""A harness timeout is a failed scheduled trial, not an excluded one.

Two full successes and one timeout on the same task must give 3 scored trials,
a mean of 2/3, pass^3 false and pass@3 true. Only adapter exit 75 (provider or
network failure) is infrastructure and may be excluded.

    python tests/test_timeout_accounting.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import make_task, run_bench, write_adapter  # noqa: E402

FLAKY = '''import json, os, sys, time
from pathlib import Path
box = Path(sys.argv[1]); c = Path(os.environ["SHB_TEST_COUNTER"])
n = int(c.read_text()) + 1 if c.exists() else 1
c.write_text(str(n))
# Trial 3 writes a valid full-credit answer FIRST, then hangs past the deadline: it must still score 0.
(box / "answer.json").write_text(json.dumps({"ok": "yes"}))
if n == 3:
    time.sleep(6)
'''


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    gold = {"grader": "checks", "checks": [{"type": "answer_equals", "key": "ok", "value": "yes"}]}
    make_task(tmp / "tasks", "respond", "cap-timeout", gold, time_limit_s=2)
    adapter = write_adapter(tmp / "flaky.py", FLAKY)
    fails = []
    for track_task in ("respond",):
        (tmp / "count").unlink(missing_ok=True)
        env = {**os.environ, "SHB_TEST_COUNTER": str(tmp / "count")}
        res = run_bench(tmp / "tasks", adapter, "--track", track_task, "--trials", "3", "--retries", "0", env=env)
        pt = {p["task"]: p for p in res["per_task"]}["cap-timeout"]
        if pt["trials"] != 3:
            fails.append(f"timeout trial was dropped: trials={pt['trials']} (expected 3)")
        if abs(pt["score"] - 2 / 3) > 1e-3:
            fails.append(f"mean must be 2/3 with one timeout, got {pt['score']}")
        if res["reliability"]["pass_at_k"] != 1:
            fails.append(f"pass@3 must be true (two full successes), got {res['reliability']['pass_at_k']}")
        if res["reliability"]["pass_hat_k"] != 0:
            fails.append(f"pass^3 must be false, got {res['reliability']['pass_hat_k']}")
        if res["infra"]["excluded"] != 0:
            fails.append(f"a harness timeout is not infrastructure: excluded={res['infra']['excluded']}")
        if res["infra"].get("scored_harness_failures") != 1:
            fails.append(f"the timeout must be reported: scored_harness_failures={res['infra'].get('scored_harness_failures')}")
    print("\n".join(fails) if fails else "timeout accounting OK: 3 trials scored, mean 2/3, pass^3 false")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
