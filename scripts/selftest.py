"""End-to-end self-test for the Phase 0 scripts, on the fictional demo dataset.

What it does (never touches your real repo):
1. Copies the repo into a temp folder (no .git, no generated files, and none
   of the real wiki/, raw/, reps/ or log/ files), runs `git init` there with
   a test identity and installs examples/demo/ into place.
2. Runs the scripts as subprocesses and checks the results:
   frontmatter helpers, guard cases, lint (clean + broken), find --owner me,
   build_index, build_books, session_start (rep, manager, unknown user),
   sync (commit only, push to a bare remote, conflict handling),
   sync_skills (drift detection and repair).
3. Prints a PASS/FAIL table and exits 1 if anything failed.

"Today" is fixed to 2026-11-03 (env MAMA_TODAY) so the demo numbers are stable.

    python3 scripts/selftest.py
    python3 scripts/selftest.py --keep      # keep the temp folder for inspection
    python3 scripts/selftest.py -v          # show output of failing steps
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mama_common as mc  # noqa: E402

TODAY = "2026-11-03"
GIT_ID = {"name": "Mama Selftest", "email": "selftest@example.com"}
DATA_DIRS = ("wiki", "raw", "reps", "log")  # real data here is never copied
MEI, ARUN, GRACE = "mei@example.com", "arun@example.com", "grace@example.com"


class Runner:
    def __init__(self, root: Path, verbose: bool):
        self.root = root
        self.verbose = verbose
        self.results: list[tuple[str, bool, str]] = []

    def env(self, email: str | None = None, **extra) -> dict:
        e = dict(os.environ)
        for k in ("MAMA_USER_EMAIL", "MAMA_ROOT", "MAMA_TODAY", "GIT_DIR", "GIT_WORK_TREE",
                  "GIT_INDEX_FILE"):
            e.pop(k, None)
        e["MAMA_ROOT"] = str(self.root)
        e["MAMA_TODAY"] = TODAY
        e["PYTHONDONTWRITEBYTECODE"] = "1"
        e["PYTHONIOENCODING"] = "utf-8"
        if email:
            e["MAMA_USER_EMAIL"] = email
        e.update(extra)
        return e

    def py(self, script: str, *args: str, email: str | None = None, stdin: str | None = None,
           cwd: Path | None = None) -> tuple[int, str, str]:
        proc = subprocess.run(
            [sys.executable, str(self.root / "scripts" / script), *args],
            cwd=str(cwd or self.root), input=stdin, capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=self.env(email), timeout=300)
        return proc.returncode, proc.stdout, proc.stderr

    def git(self, *args: str, cwd: Path | None = None) -> tuple[int, str, str]:
        return mc.run_git(list(args), cwd=cwd or self.root, timeout=120)

    def record(self, name: str, ok: bool, detail: str = "", output: str = "") -> bool:
        self.results.append((name, ok, detail))
        if not ok and self.verbose and output:
            print(f"--- output of failing step: {name}\n{output.strip()[:3000]}\n---")
        return ok


# ----------------------------------------------------------------------------
# Setup
# ----------------------------------------------------------------------------
def _ignore(src_root: Path):
    def ignore(dirpath: str, names: list[str]) -> set[str]:
        rel = Path(dirpath).resolve().relative_to(src_root).as_posix()
        skip = {n for n in names if n in (".git", "__pycache__", ".DS_Store") or n.endswith(".pyc")}
        top = rel.split("/")[0] if rel != "." else ""
        if top in DATA_DIRS:
            # keep the folder tree and .gitkeep files, drop real data
            skip |= {n for n in names if not (Path(dirpath) / n).is_dir() and n != ".gitkeep"}
            if rel == "wiki":
                skip |= {"books"}
        if rel == "runner":
            skip |= {"logs"}
        if rel == ".claude":
            skip |= {"settings.local.json"}
        return skip
    return ignore


def _rmtree(path: Path) -> None:
    def onerror(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:  # noqa: BLE001
            pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=lambda f, p, e: onerror(f, p, e))
    else:
        shutil.rmtree(path, onerror=onerror)


def setup(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=_ignore(src.resolve()))
    demo = src / "examples" / "demo"
    if not demo.is_dir():
        raise RuntimeError("examples/demo/ is missing")
    for item in demo.rglob("*"):
        if item.is_file():
            target = dst / item.relative_to(demo)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, target)
    headers = {
        "wiki/log.md": "# Sales Mama log\n",
        "wiki/suppression.csv": "value,type,reason,added_by,added_on\n",
        "log/touches.csv": ",".join(mc.TOUCH_FIELDS) + "\n",
        "log/signals.csv": "ts,source,source_type,url,snapshot,company_text,account,match_conf,"
                           "signal,status,run\n",
        "log/review.csv": "ts,signal_row,company_text,candidates,decision,decided_by,decided_on\n",
    }
    for rel, text in headers.items():
        p = dst / rel
        if not p.is_file():
            mc.write_text(p, text)
    # Manager-queue fixtures: one undecided review row, one pending proposal, one brief.
    with open(dst / "log" / "review.csv", "a", encoding="utf-8", newline="") as fh:
        fh.write("2026-11-03 02:10,7,Harbour Light Food Services,harbourlight-foods:0.82,,,\n")
    mc.write_text(dst / "log" / "allocation" / f"{TODAY}.md",
                  "# Allocation proposal (demo)\n\n- peacock-parcel-co -> arun\n")
    mc.write_text(dst / "log" / "briefs" / f"{TODAY}-manager.md", "# Manager brief (demo)\n")
    # Generated / local files must never be committed by sync.
    gi = dst / ".gitignore"
    if not gi.is_file():
        mc.write_text(gi, "wiki/index.md\nwiki/books/\nrunner/logs/\n__pycache__/\n*.pyc\n")
    # Install the skills mirror so lint's mirror check reflects the demo, not the real repo.
    subprocess.run([sys.executable, str(dst / "scripts" / "sync_skills.py")], cwd=str(dst),
                   capture_output=True, env={**os.environ, "MAMA_ROOT": str(dst)}, timeout=120)
    git_init(dst)


def git_init(path: Path, bare: bool = False) -> None:
    mc.run_git(["init", "-q", *(["--bare"] if bare else [])], cwd=path)
    mc.run_git(["symbolic-ref", "HEAD", "refs/heads/main"], cwd=path)
    if bare:
        return
    for k, v in (("user.name", GIT_ID["name"]), ("user.email", GIT_ID["email"]),
                 ("commit.gpgsign", "false"), ("core.autocrlf", "false"),
                 ("pull.rebase", "true")):
        mc.run_git(["config", k, v], cwd=path)


# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------
def t_frontmatter(r: Runner) -> None:
    p = r.root / "scratch-fm.md"
    body = "# Title\n\n## Section\ntext with --- dashes\n\n---\nnot frontmatter\n"
    text = "---\ntype: account   # keep me\nid: x\nsignals: [a]\nowner:\n---\n" + body
    mc.write_text(p, text)
    page = mc.read_page(p, r.root)
    ok = page is not None and page.meta == {"type": "account", "id": "x", "signals": ["a"],
                                            "owner": None} and page.body == body
    mc.update_frontmatter(p, {"owner": "mei", "stage": "new"})
    after = mc.read_text(p)
    page2 = mc.read_page(p, r.root)
    ok = ok and page2.body == body and page2.meta.get("owner") == "mei" \
        and page2.meta.get("stage") == "new" and "# keep me" in after
    mc.write_page(p, {"type": "contact", "id": "y"}, body)
    page3 = mc.read_page(p, r.root)
    ok = ok and page3.body == body and page3.meta == {"type": "contact", "id": "y"}
    p.unlink()
    r.record("mama_common: frontmatter keeps body", ok)
    r.record("mama_common: slugify / legal_slug",
             mc.slugify("Café & Co. (S)") == "cafe-and-co-s"
             and mc.legal_slug("Harbourlight Foods Pte Ltd") == "harbourlight-foods"
             and mc.legal_slug("Seri Kasih Catering Sdn Bhd", "MY", {"seri-kasih-catering"})
             == "seri-kasih-catering-my")
    code, out, err = mc.run_git(["definitely-not-a-git-command"], cwd=r.root)
    r.record("mama_common: run_git never raises", code != 0 and isinstance(err, str))


def guard_case(r: Runner, name: str, expect: int, email: str | None, payload: dict | str,
               cwd: Path | None = None) -> None:
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    code, out, err = r.py("guard.py", email=email, stdin=stdin, cwd=cwd)
    reason_ok = (expect != 2) or bool(err.strip())
    r.record(f"guard: {name}", code == expect and reason_ok, f"exit {code}, want {expect}",
             err + out)


def w(path: str, content: str = "x\n") -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}


def e(path: str, old: str = "a", new: str = "b") -> dict:
    return {"tool_name": "Edit", "tool_input": {"file_path": path, "old_string": old,
                                                "new_string": new}}


def t_guard(r: Runner) -> None:
    root = r.root
    guard_case(r, "rep writes knowledge/x.md -> 2", 2, MEI, w("knowledge/x.md"))
    guard_case(r, "manager writes knowledge/x.md -> 0", 0, GRACE, w("knowledge/x.md"))
    guard_case(r, "rep edits scripts/ (abs path) -> 2", 2, MEI,
               e(str(root / "scripts" / "lint.py")))
    guard_case(r, "rep edits CLAUDE.md via MultiEdit -> 2", 2, ARUN,
               {"tool_name": "MultiEdit", "tool_input": {"file_path": "CLAUDE.md",
                                                         "edits": [{"old_string": "a",
                                                                    "new_string": "b"}]}})
    guard_case(r, "rep writes .claude\\settings.json (backslashes) -> 2", 2, MEI,
               w(".claude\\settings.json"))
    guard_case(r, "unknown user writes AGENTS.md -> 2", 2, "nobody@example.com", w("AGENTS.md"))
    raw_existing = "raw/research/harbourlight-foods/2026-10-20-site.md"
    guard_case(r, "rep edits existing raw file -> 2", 2, MEI, e(raw_existing))
    guard_case(r, "manager edits existing raw file -> 2", 2, GRACE, e(raw_existing))
    guard_case(r, "rep creates new raw file -> 0", 0, MEI,
               w("raw/notes/2026-11-03-harbourlight-foods-call.md"))
    guard_case(r, "rep edits another rep's account -> 2", 2, MEI,
               e("wiki/accounts/seri-kasih-catering.md"))
    guard_case(r, "rep edits own account -> 0", 0, MEI, e("wiki/accounts/harbourlight-foods.md"))
    guard_case(r, "rep edits pool account -> 0", 0, MEI, e("wiki/accounts/lantern-lane-bakery.md"))
    guard_case(r, "manager edits any account -> 0", 0, GRACE,
               e("wiki/accounts/seri-kasih-catering.md"))
    guard_case(r, "rep edits own reps file -> 0", 0, MEI, e("reps/mei.md", "tone:", "tone: x"))
    guard_case(r, "rep edits another rep's file -> 2", 2, MEI, e("reps/arun.md"))
    guard_case(r, "rep sets role: manager on self -> 2", 2, MEI,
               e("reps/mei.md", "role: rep", "role: manager"))
    guard_case(r, "new user creates reps/<id>.md role: rep -> 0", 0, "newbie@example.com",
               w("reps/newbie.md", "---\ntype: rep\nid: newbie\nemail: newbie@example.com\n"
                                   "role: rep\n---\n# Newbie\n"))
    guard_case(r, "new user creates reps file role: manager -> 2", 2, "newbie@example.com",
               w("reps/newbie.md", "---\ntype: rep\nid: newbie\nrole: manager\n---\n"))
    guard_case(r, "path outside repo -> 0", 0, MEI,
               w(str(Path(tempfile.gettempdir()) / "mama-outside.md")))
    guard_case(r, "malformed JSON -> 0 (fail open)", 0, MEI, "{not json")
    guard_case(r, "non-write tool -> 0", 0, MEI,
               {"tool_name": "Read", "tool_input": {"file_path": "knowledge/x.md"}})
    guard_case(r, "relative path with hook cwd -> 2", 2, MEI,
               {"tool_name": "Write", "cwd": str(root / "knowledge"),
                "tool_input": {"file_path": "y.md", "content": "x"}})

    # Bootstrap: no rep files -> everything allowed.
    reps = root / "reps"
    hold = root / "reps-hold"
    reps.rename(hold)
    try:
        reps.mkdir()
        guard_case(r, "bootstrap (empty reps/) rep writes knowledge -> 0", 0, MEI,
                   w("knowledge/x.md"))
    finally:
        shutil.rmtree(reps)
        hold.rename(reps)


def t_lint(r: Runner) -> None:
    code, out, err = r.py("lint.py")
    r.record("lint: demo exits 0", code == 0, f"exit {code}", out + err)
    code, out, err = r.py("lint.py", "--json")
    try:
        data = json.loads(out)
        ok = code == 0 and data["errors"] == 0 and isinstance(data["items"], list)
    except Exception:  # noqa: BLE001
        ok = False
    r.record("lint: --json is valid", ok, f"exit {code}", out + err)

    acc = r.root / "wiki" / "accounts" / "peacock-parcel-co.md"
    original = mc.read_text(acc)
    mc.write_text(acc, original.replace("reg_id: UDYAM-KA-03-0001234", "reg_id: UDYAM-KA-3-1234")
                  .replace("market: IN ", "market:    "))
    bad_signal = r.root / "wiki" / "accounts" / "lumen-logistics.md"
    sig_orig = mc.read_text(bad_signal)
    mc.write_text(bad_signal, sig_orig.replace(
        "## Pains & hypotheses", "- hiring_ops_it — saw a job post, no link\n## Pains & hypotheses", 1))
    try:
        code, out, err = r.py("lint.py", "--json")
        try:
            data = json.loads(out)
            checks = {(i["check"], i["path"]) for i in data["items"] if i["level"] == "error"}
        except Exception:  # noqa: BLE001
            checks = set()
        ok = code == 1 and ("registry", "wiki/accounts/peacock-parcel-co.md") in checks \
            and ("market", "wiki/accounts/peacock-parcel-co.md") in checks \
            and ("signals", "wiki/accounts/lumen-logistics.md") in checks
        r.record("lint: bad reg_id / no market / unsourced signal -> 1", ok, f"exit {code}",
                 out + err)
    finally:
        mc.write_text(acc, original)
        mc.write_text(bad_signal, sig_orig)

    # Registry formats, directly.
    import lint
    good = {"uen": ["201912345K", "53312345A"], "ssm": ["202301012345"],
            "cin": ["U63090KA2019PTC123456"], "llpin": ["AAB-1234"],
            "gstin": ["29ABCDE1234F1Z5"], "udyam": ["UDYAM-KA-03-0001234"]}
    bad = {"uen": ["2019123456", "12345A"], "ssm": ["20230101234"], "cin": ["U63090KA2019PTC12345"],
           "llpin": ["AB-1234", "AAB1234"], "gstin": ["29ABCDE1234F1Z"], "udyam": ["UDYAM-KA-3-1234"]}
    ok = all(lint.REG_PATTERNS[k][0].match(v) for k, vs in good.items() for v in vs) and \
        not any(lint.REG_PATTERNS[k][0].match(v) for k, vs in bad.items() for v in vs)
    r.record("lint: registry-ID formats", ok)


def t_find(r: Runner) -> None:
    code, out, err = r.py("find.py", "--owner", "me", "--json", email=MEI)
    try:
        ids = {row["id"] for row in json.loads(out)}
    except Exception:  # noqa: BLE001
        ids = set()
    r.record("find: --owner me returns only own accounts",
             code == 0 and ids == {"harbourlight-foods", "nimbus-clinics"}, f"got {sorted(ids)}",
             out + err)
    code, out, err = r.py("find.py", "--owner", "none", "--tier", "B", "--market", "IN", "--json")
    try:
        ids = [row["id"] for row in json.loads(out)]
    except Exception:  # noqa: BLE001
        ids = []
    r.record("find: --owner none --tier B --market IN", ids == ["peacock-parcel-co"], str(ids),
             out + err)
    code, out, err = r.py("find.py", "--signal", "contract_win", "--due-before", TODAY, "--json")
    try:
        ids = [row["id"] for row in json.loads(out)]
    except Exception:  # noqa: BLE001
        ids = []
    r.record("find: --signal + --due-before", ids == ["harbourlight-foods"], str(ids), out + err)
    code, out, err = r.py("find.py", "--hot", "--json")
    try:
        ids = sorted(row["id"] for row in json.loads(out))
    except Exception:  # noqa: BLE001
        ids = []
    r.record("find: --hot (risk flag or tier A scored today)",
             ids == ["harbourlight-foods", "seri-kasih-catering"], str(ids), out + err)
    code, out, err = r.py("find.py", "--type", "contact", "--text", "BUSINESS NUMBER FOR WhatsApp")
    r.record("find: --type contact --text (table)",
             code == 0 and "farid-rahman-seri-kasih-catering" in out and "(1 match)" in out,
             f"exit {code}", out + err)


def t_index(r: Runner) -> None:
    code, out, err = r.py("build_index.py")
    p = r.root / "wiki" / "index.md"
    text = mc.read_text(p) if p.is_file() else ""
    ok = code == 0 and "Accounts: **6**" in text and "Contacts: **2**" in text \
        and "### mei" in text and "### (pool)" in text \
        and "[[accounts/harbourlight-foods]] Harbourlight Foods Pte Ltd · SG · tier A · meeting · due 2026-11-03" in text \
        and "already-have-provider" in text and "| objection | draft | 1 |" in text
    r.record("build_index: wiki/index.md", ok, f"exit {code}", out + err + text[:1500])


def t_books(r: Runner) -> None:
    code, out, err = r.py("build_books.py")
    books = r.root / "wiki" / "books"
    mei = mc.read_text(books / "mei.md") if (books / "mei.md").is_file() else ""
    arun = mc.read_text(books / "arun.md") if (books / "arun.md").is_file() else ""
    team = mc.read_text(books / "team.md") if (books / "team.md").is_file() else ""
    r.record("build_books: files exist", code == 0 and bool(mei and arun and team)
             and (books / "grace.md").is_file(), f"exit {code}", out + err)
    r.record("build_books: mei numbers",
             "Active accounts: **2 / 40**" in mei and "Meetings this month: **1 / 8**" in mei
             and "**1 replies / 2 sent**" in mei and "## Today — due actions (2)" in mei
             and "## Hot (1)" in mei and "## At risk (1)" in mei and "contract_ending_no_plan" in mei
             and mei.index("harbourlight-foods") < mei.index("nimbus-clinics")
             and "Prep the call brief" in mei, "", mei)
    r.record("build_books: arun numbers",
             "Active accounts: **2 / 50**" in arun and "Meetings this month: **0 / 6**" in arun
             and "**1 replies / 1 sent**" in arun and "## Today — due actions (1)" in arun
             and "## Hot (1)" in arun and "## VAM pre-drafts waiting (1)" in arun, "", arun)
    r.record("build_books: team table + pool",
             "Pool (unowned, active): 2" in team and "A 0 · B 1 · C 1" in team
             and "| 2 / 40 | 1 | 1 | 0 | 2 | 1 | 1 / 8 | 2 | 1 |" in team
             and "Review queue: 1 undecided" in team, "", team)


def t_session(r: Runner) -> None:
    code, out, err = r.py("session_start.py", email=MEI)
    r.record("session_start: rep exit 0 + queue",
             code == 0 and "Sales Mama ready" in out and "Due or overdue (2)" in out
             and "Quota left today: 15 / 15" in out and "VAM pre-drafts waiting (1)" in out,
             f"exit {code}", out + err)
    code, out, err = r.py("session_start.py", email=ARUN)
    r.record("session_start: quota counts today's drafts",
             code == 0 and "Quota left today: 11 / 12" in out, f"exit {code}", out + err)
    code, out, err = r.py("session_start.py", email=GRACE)
    r.record("session_start: manager queue",
             code == 0 and "Manager queue" in out and "Allocation proposals pending: 1" in out
             and "Review queue: 1 undecided" in out
             and f"Latest brief: log/briefs/{TODAY}-manager.md" in out, f"exit {code}", out + err)
    code, out, err = r.py("session_start.py", email="stranger@example.com")
    r.record("session_start: unknown user -> Run mama-setup",
             code == 0 and "Run mama-setup" in out, f"exit {code}", out + err)
    code, out, err = r.py("session_start.py", "--bogus-flag", email=MEI)
    r.record("session_start: bad args still exit 0", code == 0, f"exit {code}", out + err)
    r.record("session_start: rebuilt index and books",
             (r.root / "wiki" / "index.md").is_file() and (r.root / "wiki" / "books" / "team.md").is_file())


def t_sync(r: Runner) -> None:
    root = r.root
    r.git("add", "-A")
    code, out, err = r.git("commit", "-q", "-m", "chore: bootstrap Sales Mama (selftest)")
    if not r.record("sync: initial commit for test", code == 0, err.strip()[:80], out + err):
        return
    mc.write_text(root / "wiki" / "log.md",
                  mc.read_text(root / "wiki" / "log.md") + "- [2026-11-03 09:00] research | mei | harbourlight-foods | selftest\n")
    mc.write_text(root / "raw" / "notes" / "2026-11-03-selftest.md", "# selftest note\n")
    mc.write_text(root / "knowledge" / "selftest.md", "must not be committed by sync\n")
    _, head_before, _ = r.git("rev-parse", "HEAD")
    code, out, err = r.py("sync.py", email=MEI)
    _, head_after, _ = r.git("rev-parse", "HEAD")
    _, subject, _ = r.git("log", "-1", "--format=%s")
    _, files, _ = r.git("show", "--name-only", "--format=", "HEAD")
    _, status, _ = r.git("status", "--porcelain")
    ok = code == 0 and head_before != head_after and subject.startswith("mama(mei): ") \
        and "wiki/log.md" in files and "raw/notes/2026-11-03-selftest.md" in files \
        and "knowledge/selftest.md" not in files and "wiki/index.md" not in files \
        and "wiki/books" not in files and "knowledge/selftest.md" in status \
        and "no git remote" in out
    r.record("sync: commits only wiki/raw/log/reps (no remote)", ok,
             subject.strip()[:60], out + err + files + status)
    (root / "knowledge" / "selftest.md").unlink()
    code, out, err = r.py("sync.py", "--quiet", email=MEI)
    r.record("sync: nothing to do -> exit 0, quiet", code == 0 and out.strip() == "",
             f"exit {code}", out + err)

    # With a remote: push, then a conflicting teammate change.
    tmp = root.parent
    remote = tmp / "remote.git"
    remote.mkdir()
    git_init(remote, bare=True)
    r.git("remote", "add", "origin", str(remote))
    code, out, err = r.py("sync.py", email=MEI)
    _, rhead, _ = r.git("rev-parse", "main", cwd=remote)
    _, lhead, _ = r.git("rev-parse", "HEAD")
    r.record("sync: first push sets upstream", code == 0 and rhead.strip() == lhead.strip()
             and bool(mc.git_upstream(root)), f"exit {code}", out + err)

    other = tmp / "teammate"
    mc.run_git(["clone", "-q", str(remote), str(other)], cwd=tmp)
    for k, v in (("user.name", "Teammate"), ("user.email", "arun@example.com"),
                 ("commit.gpgsign", "false")):
        mc.run_git(["config", k, v], cwd=other)
    target = "wiki/accounts/lantern-lane-bakery.md"
    t_other = other / target
    mc.write_text(t_other, mc.read_text(t_other).replace("employees: 12", "employees: 14"))
    mc.run_git(["commit", "-qam", "mama(arun): teammate edit"], cwd=other)
    mc.run_git(["push", "-q"], cwd=other)

    # Non-conflicting local change -> rebase + push works.
    mc.write_text(root / "raw" / "notes" / "2026-11-03-second.md", "# second\n")
    code, out, err = r.py("sync.py", email=MEI)
    _, rhead, _ = r.git("rev-parse", "main", cwd=remote)
    _, lhead, _ = r.git("rev-parse", "HEAD")
    r.record("sync: pull --rebase then push", code == 0 and rhead.strip() == lhead.strip()
             and "employees: 14" in mc.read_text(root / target), f"exit {code}", out + err)

    # Conflict: both change the same line.
    mc.run_git(["pull", "-q", "--rebase"], cwd=other)
    mc.write_text(t_other, mc.read_text(t_other).replace("employees: 14", "employees: 20"))
    mc.run_git(["commit", "-qam", "mama(arun): conflicting edit"], cwd=other)
    mc.run_git(["push", "-q"], cwd=other)
    t_local = root / target
    mc.write_text(t_local, mc.read_text(t_local).replace("employees: 14", "employees: 99"))
    code, out, err = r.py("sync.py", email=MEI)
    _, subject, _ = r.git("log", "-1", "--format=%s")
    _, rhead, _ = r.git("rev-parse", "main", cwd=remote)
    ok = code == 0 and "Sync conflict" in out and not mc.rebase_in_progress(root) \
        and subject.startswith("mama(mei): ") and "employees: 99" in mc.read_text(t_local) \
        and "employees: 20" in mc.read_text(t_other) and target in out
    _, remote_file, _ = r.git("show", f"main:{target}", cwd=remote)
    ok = ok and "employees: 20" in remote_file
    r.record("sync: conflict aborts rebase, keeps local commit, never forces", ok,
             f"exit {code}", out + err)


def t_skills(r: Runner) -> None:
    code, out, err = r.py("sync_skills.py", "--check")
    r.record("sync_skills: --check clean -> 0", code == 0, f"exit {code}", out + err)
    src = r.root / ".agents" / "skills" / "zz-selftest" / "SKILL.md"
    stale = r.root / ".claude" / "skills" / "zz-stale" / "SKILL.md"
    mc.write_text(src, "---\nname: zz-selftest\ndescription: test\n---\nbody\n")
    mc.write_text(stale, "stale\n")
    code, out, err = r.py("sync_skills.py", "--check")
    r.record("sync_skills: --check drift -> 1", code == 1 and "zz-selftest" in out
             and "zz-stale" in out, f"exit {code}", out + err)
    code, out, err = r.py("lint.py")
    r.record("lint: skills drift is an error", code == 1 and "[skills]" in out, f"exit {code}",
             out + err)
    code, out, err = r.py("sync_skills.py")
    mirror = r.root / ".claude" / "skills" / "zz-selftest" / "SKILL.md"
    ok = code == 0 and mirror.is_file() and not mirror.is_symlink() and not stale.exists() \
        and not stale.parent.exists()
    code2, out2, err2 = r.py("sync_skills.py", "--check")
    r.record("sync_skills: copy + prune, then --check -> 0", ok and code2 == 0,
             f"exit {code}/{code2}", out + err + out2 + err2)
    shutil.rmtree(src.parent)
    r.py("sync_skills.py")


def t_help(r: Runner) -> None:
    bad = []
    for s in ("mama_common.py", "session_start.py", "sync.py", "build_index.py",
              "build_books.py", "find.py", "guard.py", "lint.py", "sync_skills.py"):
        code, out, _ = r.py(s, "--help")
        if code != 0 or "usage" not in out.lower():
            bad.append(s)
    r.record("all scripts: --help", not bad, ", ".join(bad))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Self-test the Sales Mama scripts on examples/demo "
                                             "in a temporary copy of the repo.")
    ap.add_argument("--keep", action="store_true", help="keep the temp folder")
    ap.add_argument("-v", "--verbose", action="store_true", help="print output of failing steps")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    src = mc.repo_root()
    tmp = Path(tempfile.mkdtemp(prefix="mama-selftest-"))
    root = tmp / "repo"
    runner = Runner(root, args.verbose)
    try:
        setup(src, root)
        sys.path.insert(0, str(root / "scripts"))
        for test in (t_help, t_frontmatter, t_guard, t_lint, t_find, t_index, t_books, t_session,
                     t_sync, t_skills):
            try:
                test(runner)
            except Exception as exc:  # noqa: BLE001
                runner.record(f"{test.__name__}: crashed", False, f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001
        runner.record("setup", False, f"{type(exc).__name__}: {exc}")
    finally:
        if args.keep:
            print(f"Temp folder kept: {tmp}")
        else:
            _rmtree(tmp)

    width = max(len(n) for n, _, _ in runner.results)
    print(f"{'Check'.ljust(width)}  Result  Detail")
    print(f"{'-' * width}  ------  ------")
    for name, ok, detail in runner.results:
        print(f"{name.ljust(width)}  {'PASS' if ok else 'FAIL':6}  {'' if ok else detail}".rstrip())
    failed = sum(1 for _, ok, _ in runner.results if not ok)
    print(f"\n{len(runner.results) - failed}/{len(runner.results)} passed"
          + (f", {failed} FAILED" if failed else " — all good"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
