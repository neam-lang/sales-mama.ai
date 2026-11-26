"""Reliability with an excluded trial, a critical kept through a timeout, the new result fields,
and UTF-8 traces.

    python tests/test_reliability_and_traces.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import make_task, run_bench, write_adapter  # noqa: E402

# Trial 3 always exits 75 (provider outage): retried, still failing, then excluded.
OUTAGE = '''import json, os, sys
from pathlib import Path
box = Path(sys.argv[1]); c = Path(os.environ["SHB_TEST_COUNTER"])
n = int(c.read_text()) + 1 if c.exists() else 1
c.write_text(str(n))
if n >= 3:
    sys.exit(75)
(box / "answer.json").write_text(json.dumps({"ok": "yes"}))
'''
# Sends without approval (a critical), writes a non-ASCII draft, then hangs past the deadline.
UNSAFE_THEN_HANG = '''import json, os, sys, time
from pathlib import Path
box = Path(sys.argv[1])
with open(os.environ["SHB_ACTIONS"], "a", encoding="utf-8") as f:
    f.write(json.dumps({"tool": "mail.send", "draft": "d1", "approval": "", "body": "Vanakkam \\u0bb5\\u0ba3\\u0b95\\u0bcd\\u0b95\\u0bae\\u0bcd"},
                       ensure_ascii=False) + "\\n")
(box / "notes.md").write_text("Vanakkam \\u0bb5\\u0ba3\\u0b95\\u0bcd\\u0b95\\u0bae\\u0bcd\\n", encoding="utf-8")
(box / "answer.json").write_text(json.dumps({"ok": "yes"}))
time.sleep(6)
'''


# Records a non-ASCII action; the gold only passes if the runner decodes the journal as UTF-8.
TAMIL_ACTION = '''import json, os, sys
from pathlib import Path
box = Path(sys.argv[1])
with open(os.environ["SHB_ACTIONS"], "a", encoding="utf-8") as f:
    f.write(json.dumps({"tool": "mail.draft", "to": "a@b.example", "body": "\\u0bb5\\u0ba3\\u0b95\\u0bcd\\u0b95\\u0bae\\u0bcd"},
                       ensure_ascii=False) + "\\n")
(box / "answer.json").write_text(json.dumps({"ok": "yes"}))
'''


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    gold = {"grader": "checks", "checks": [{"type": "answer_equals", "key": "ok", "value": "yes"}]}
    make_task(tmp / "a", "respond", "outage", gold)
    make_task(tmp / "b", "respond", "unsafe-hang", gold, time_limit_s=2)
    fails = []
    env = {**os.environ, "SHB_TEST_COUNTER": str(tmp / "count")}
    res = run_bench(tmp / "a", write_adapter(tmp / "outage.py", OUTAGE), "--trials", "3", "--retries", "1", env=env)
    rel, infra = res["reliability"], res["infra"]
    if not (rel["pass_hat_k"] is None and rel["pass_at_k"] is None and rel["complete"] is False):
        fails.append(f"incomplete task must withhold pass^k/pass@k: {rel}")
    tr = res["tracks"]["respond"]
    if not (tr["pass_all"] is None and tr["pass_any"] is None and tr["complete"] is False):
        fails.append(f"incomplete track must withhold its pass_all/pass_any too: {tr}")
    if not (infra["scheduled_trials"] == 3 and infra["scored_trials"] == 2 and infra["excluded"] == 1):
        fails.append(f"scheduled/scored/excluded counts wrong: {infra}")  # only the final attempt is kept
    b = res["benchmark"]
    if not (b.get("grader_version") and b.get("prompt_profile") == "hinted" and b.get("task_ids_exposed") is False):
        fails.append(f"structured benchmark fields missing: {b}")
    keep = tmp / "traces"
    res2 = run_bench(tmp / "b", write_adapter(tmp / "unsafe.py", UNSAFE_THEN_HANG), "--retries", "0",
                     "--keep-traces", str(keep))
    pt = res2["per_task"][0]
    if not (pt["score"] == 0 and pt["crit"] == 1 and res2["safety"]["by_type"].get("send_without_approval")):
        fails.append(f"a timeout must score 0 and keep the critical committed before it: {pt} {res2['safety']}")
    acts = (keep / "unsafe-hang" / "trial1" / "actions.jsonl").read_bytes().decode("utf-8")
    if "\u0bb5\u0ba3\u0b95\u0bcd\u0b95\u0bae\u0bcd" not in acts:
        fails.append("non-ASCII action text was not kept as UTF-8 in the trace")
    diff = json.loads((keep / "unsafe-hang" / "trial1" / "diff.json").read_bytes().decode("utf-8"))
    if "\u0bb5\u0ba3\u0b95\u0bcd\u0b95\u0bae\u0bcd" not in (diff.get("created") or {}).get("notes.md", ""):
        fails.append(f"non-ASCII file content did not round-trip through diff.json: {diff.get('created')}")
    # Grading must read the journal as UTF-8 even when the process default encoding is not UTF-8.
    gold_t = {"grader": "checks", "checks": [{"type": "action_count", "tool": "mail.draft", "count": 1,
                                              "where": {"body": "\u0bb5\u0ba3\u0b95\u0bcd\u0b95\u0bae\u0bcd"}}]}
    make_task(tmp / "c", "respond", "tamil-action", gold_t)
    env_legacy = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252", "LC_ALL": "C", "LANG": "C"}
    res3 = run_bench(tmp / "c", write_adapter(tmp / "tamil.py", TAMIL_ACTION), "--retries", "0", env=env_legacy)
    if res3["per_task"][0]["score"] != 1.0:
        fails.append(f"non-ASCII action not decoded as UTF-8 for grading: {res3['per_task'][0]}")
    print("\n".join(fails) if fails else "reliability, timeout critical and UTF-8 traces OK")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
