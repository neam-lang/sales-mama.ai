"""The generated bin/mama-tool wrapper (POSIX only; Windows runs tool.py through Python) records a call.

    python tests/test_posix_wrapper.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shb.run import make_tool  # noqa: E402


def main() -> int:
    if os.name == "nt":
        print("posix wrapper: skipped on Windows")
        return 0
    tmp = Path(tempfile.mkdtemp())
    make_tool(tmp / "bin")
    log = tmp / "actions.jsonl"
    log.write_text("")
    env = {**os.environ, "SHB_ACTIONS": str(log), "PATH": f"{tmp / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"}
    cp = subprocess.run(["mama-tool", "crm", "update", "--account", "acme", "--field", "stage=contacted"],
                        cwd=tmp, env=env, capture_output=True, text=True)
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    ok = cp.returncode == 0 and len(rows) == 1 and rows[0].get("tool") == "crm.update"
    print("posix wrapper OK: mama-tool on PATH records the call" if ok else f"FAIL: {cp.returncode} {cp.stderr} {rows}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
