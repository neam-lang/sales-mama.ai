"""End-to-end self-test for the Sales Mama scripts, on the fictional demo dataset.

What it does (never touches your real repo):
1. Copies the repo into a temp folder (no .git, no generated files, and none
   of the real wiki/, raw/, reps/ or log/ files), runs `git init` there with
   a test identity and installs examples/demo/ into place.
2. Runs the scripts as subprocesses and checks the results:
   frontmatter helpers, guard cases, lint (clean + broken), find --owner me,
   build_index, build_books, session_start (rep, manager, unknown user),
   sync (commit only, push to a bare remote, conflict handling),
   sync_skills (drift detection and repair), ingest (CRM export -> 50
   accounts, dedupe, contract dates, owner kept), score (deterministic parts,
   ownership, hot flag), recommend (owned / size / decay / negative / ties),
   eval (pass + planted failures, golden recommendation match), draft_check
   (owner, suppression, entities, contract timing, send window), classify_reply,
   suppress (unsubscribe -> suppression.csv -> draft refused), claim (rules,
   assign/release/reassign, two clones racing for the same accounts -> zero
   double claims) and allocate (constraints, continuity, approve).
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
    # Golden accounts belong to the real repo, not the demo; t_eval plants its own.
    for g in (dst / "evals" / "golden_accounts").glob("*.md"):
        if not g.name.startswith("_"):
            g.unlink()
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
    guard_case(r, "rep writes .env -> 2 (secrets)", 2, MEI, w(".env", "X=1\n"))
    guard_case(r, "manager writes gmail.json -> 2 (secrets)", 2, GRACE, w("notes/gmail.json", "{}"))
    guard_case(r, "manager writes text with an access token -> 2", 2, GRACE,
               w("wiki/notes.md", "token ya29." + "a" * 40 + "\n"))
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


def t_lint_secrets(r: Runner) -> None:
    leak = r.root / "wiki" / "leak-note.md"
    mc.write_text(leak, "pasted by mistake: ya29." + "b" * 40 + "\n")
    try:
        code, out, err = r.py("lint.py", "--json")
        items = [i for i in _json(out).get("items", []) if i.get("check") == "secrets"]
        r.record("lint: a token in the repo -> secrets error", code == 1 and len(items) == 1, out[-500:])
    finally:
        leak.unlink()


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


EXPORT = "raw/crm/2026-11-01-demo-export-50.csv"


def _json(out: str) -> dict:
    try:
        return json.loads(out)
    except Exception:  # noqa: BLE001
        return {}


def t_ingest(r: Runner) -> None:
    accounts = r.root / "wiki" / "accounts"
    raw = r.root / EXPORT
    raw_before = raw.read_bytes()
    signals_before = mc.read_text(r.root / "log" / "signals.csv")
    nimbus = accounts / "nimbus-clinics.md"
    nimbus_before = mc.read_text(nimbus)

    code, out, err = r.py("ingest.py", "crm", EXPORT, email=MEI)
    r.record("ingest: rep is refused -> 1", code == 1 and "manager only" in out, f"exit {code}",
             out + err)

    code, out, err = r.py("ingest.py", "crm", EXPORT, "--dry-run", "--json", email=GRACE)
    d = _json(out)
    ok = code == 0 and d.get("dry_run") is True and len(d.get("new", [])) == 47 \
        and len(list(accounts.glob("*.md"))) == 6 and mc.read_text(nimbus) == nimbus_before
    r.record("ingest: --dry-run writes nothing", ok, f"exit {code}", out + err)

    code, out, err = r.py("ingest.py", "crm", EXPORT, "--json", email=GRACE)
    d = _json(out)
    counts = {k: len(d.get(k, [])) for k in ("new", "updated", "duplicates", "skipped",
                                              "contract_ending")}
    want = {"new": 47, "updated": 3, "duplicates": 1, "skipped": 1, "contract_ending": 9}
    r.record("ingest: 52 rows -> 47 new, 3 updated, 1 dup, 1 skipped", code == 0 and counts == want,
             f"exit {code}, {counts}", out + err)

    pages = [mc.read_page(p, r.root) for p in sorted(accounts.glob("*.md"))]
    cited = [p for p in pages if EXPORT in p.body]
    r.record("ingest: 50 accounts cite the export (gate)", len(pages) == 53 and len(cited) == 50,
             f"{len(pages)} pages, {len(cited)} cite it")

    with_end = sum(1 for row in mc.read_csv(raw)[:-2] if row.get("Contract End"))
    mapped = sum(1 for p in cited if p.meta.get("contract_end"))
    by_id = {p.id: p.meta for p in pages}
    ok = with_end == 38 and mapped == with_end \
        and str(by_id["copperleaf-retail"].get("contract_end")) == "2027-03-31" \
        and str(by_id["nimbus-clinics"].get("contract_end")) == "2026-12-31"
    r.record("ingest: contract dates mapped (ISO and DD/MM/YYYY)", ok, f"{mapped}/{with_end}")

    n = by_id["nimbus-clinics"]
    ok = n.get("owner") == "mei" and n.get("stage") == "contacted" \
        and n.get("next_action") == "Send follow-up 1" and n.get("name") == "Nimbus Clinics Pte Ltd" \
        and n.get("employees") == 42 and n.get("products_owned") == ["cloud-phone"]
    r.record("ingest: owner/stage/next_action kept on update", ok, str({k: n.get(k) for k in
             ("owner", "stage", "next_action", "name", "employees")}))

    lh = by_id["lotus-learning-hub"]
    bb = by_id["bluefin-bistro"]
    ok = not lh.get("reg_id") and not lh.get("reg_type") and bb.get("employees") != 999 \
        and bb.get("source") == "crm" and bb.get("stage") == "new" and not bb.get("owner") \
        and 0 <= float(bb.get("propensity") or -1) <= 1 and "harbourlight-foods" in by_id \
        and "harbourlight-foods-sg" not in by_id and "siam-spice-co" not in by_id
    r.record("ingest: dedupe, invalid reg_id blank, new page defaults", ok)

    log = mc.read_text(r.root / "wiki" / "log.md")
    ok = "unmapped | grace | " + EXPORT + ' | industry "Mining"' in log \
        and 'product "Legacy PBX"' in log and f"ingest | grace | {EXPORT} | 47 new" in log
    r.record("ingest: unmapped + ingest lines logged", ok)

    ok = raw.read_bytes() == raw_before and mc.read_text(r.root / "log" / "signals.csv") == signals_before
    r.record("ingest: raw/ and log/signals.csv untouched", ok)

    code, out, err = r.py("ingest.py", "crm", EXPORT, email=GRACE)
    code2, out2, err2 = r.py("ingest.py", "crm", EXPORT, "--force", "--json", email=GRACE)
    d = _json(out2)
    ok = code == 0 and "already ingested" in out and code2 == 0 and not d.get("new") \
        and not d.get("updated")
    r.record("ingest: re-run skipped; --force changes nothing", ok, f"exit {code}/{code2}",
             out + err + out2 + err2)

    code, out, err = r.py("lint.py")
    r.record("lint: clean after ingest (gate)", code == 0, f"exit {code}", out + err)


def t_fetch(r: Runner) -> None:
    fixture = r.root.parent / "acra-fixture.json"
    row = {"_dataset": "d_fixture", "entity_type_description": "Local Company",
           "company_type_description": "Private Company Limited by Shares", "street_name": "1 SECRET ROAD"}
    rows = [
        {**row, "entity_name": "KOPI CORNER PTE. LTD.", "uen": "202640001A",
         "registration_incorporation_date": "2026-10-20", "primary_ssic_code": "56111"},
        {**row, "entity_name": "LANTERN TUITION PTE. LTD.", "uen": "202640002B",
         "registration_incorporation_date": "2026-10-18", "primary_ssic_code": "85492"},
        {**row, "entity_name": "SPRUCE RETAIL PTE. LTD.", "uen": "202640003C",
         "registration_incorporation_date": "2026-10-10", "primary_ssic_code": "47711"},
        {**row, "entity_name": "BYTEFORGE PTE. LTD.", "uen": "202640004D",            # SSIC not in ICP
         "registration_incorporation_date": "2026-10-21", "primary_ssic_code": "62011"},
        {**row, "entity_name": "KIND HEARTS LTD.", "uen": "202640005E",               # excluded type
         "registration_incorporation_date": "2026-10-21", "primary_ssic_code": "85499",
         "company_type_description": "Public Company Limited by Guarantee"},
        {**row, "entity_name": "OLD BAKERY PTE. LTD.", "uen": "202640006F",           # outside lookback
         "registration_incorporation_date": "2026-08-01", "primary_ssic_code": "56111"},
    ]
    mc.write_text(fixture, json.dumps(rows))
    code, out, err = r.py("fetch_dataset.py", "sg-acra-new-cos", "--from-file", str(fixture), "--max", "2",
                          "--json", email=GRACE)
    d = _json(out)
    items = d.get("items", [])
    names = [i.get("company_text") for i in items]
    ok = code == 0 and names == ["KOPI CORNER PTE. LTD.", "LANTERN TUITION PTE. LTD."] and d.get("capped") \
        and items[0].get("reg_id") == "202640001A" and items[0].get("industry") == "fnb" \
        and items[0].get("signal") == "new_company"
    r.record("fetch: dataset rows filtered (ICP SSIC, type, lookback) and capped", ok, f"exit {code}", out + err)
    snaps = [r.root / i.get("snapshot", "-") for i in items]
    texts = [mc.read_text(p) for p in snaps if p.is_file()]
    summaries = [t.split("## Summary", 1)[-1] for t in texts]
    ok = len(texts) == 2 and all(i["snapshot"].startswith(f"raw/signals/{TODAY}/sg-acra-new-cos/") for i in items) \
        and not any("SECRET" in t for t in texts) and all(len(s.split()) <= 60 for s in summaries)
    r.record("fetch: snapshots written, no address, summary <= 60 words", ok, f"{len(texts)} snapshots")

    code, out, err = r.py("fetch_dataset.py", "sg-crm-contract-ends", "--json", email=GRACE)
    items = _json(out).get("items", [])
    ok = code == 0 and items and all(i["market"] == "SG" and i["snapshot"] == EXPORT
                                     and i["signal"] == "contract_ending" for i in items)
    r.record("fetch: internal contract ends cite the CRM export", ok, f"exit {code}, {len(items)} items", out + err)

    src = r.root / "knowledge" / "sources.yaml"
    orig = mc.read_text(src)
    mc.write_text(src, orig + "  - {id: x-no-tos, market: SG, type: news, access: rss, url: http://x.invalid, "
                               "trust: 0.5}\n")
    try:
        code, out, err = r.py("fetch_dataset.py", "x-no-tos", email=GRACE)
        r.record("fetch: source without tos_checked refused -> 1", code == 1 and "tos_checked" in out,
                 f"exit {code}", out + err)
    finally:
        mc.write_text(src, orig)


def t_resolve(r: Runner) -> None:
    snap_dir = r.root / "raw" / "signals" / TODAY / "selftest"
    snap = f"raw/signals/{TODAY}/selftest/item.md"
    mc.write_text(r.root / snap, "# selftest item\n")
    base = {"market": "SG", "source": "selftest", "source_type": "news", "date": TODAY, "snapshot": snap}
    ev = {"name": "Selftest Expo", "year": 2026, "dates": ["2026-12-02"], "venue": "Hall 1", "url": "https://x.example"}
    items = [
        {**base, "url": "u1", "company_text": "Bluefin Bistro", "reg_id": "201215175K", "signal": "new_branch_opened",
         "headline": "Opens a second outlet"},
        {**base, "url": "u2", "company_text": "Copperleaf", "domain": "https://www.copperleafretail.example/about",
         "signal": "funding_round"},
        {**base, "url": "u3", "company_text": "Dovetail Movers Pte. Ltd.", "signal": "contract_win"},
        {**base, "url": "u4", "company_text": "Copperleaf Group", "signal": "funding_round"},
        {**base, "url": "u5", "company_text": "Bluefin Bistro Pte Ltd", "reg_id": "201899999Z",
         "industry": "fnb", "signal": "new_branch_opened"},
        {**base, "url": "u6", "company_text": "Kopi Corner Pte Ltd", "industry": "fnb", "employees": 15,
         "signal": "new_branch_opened"},
        {**base, "url": "u7", "company_text": "Ministry of Kopi", "industry": "fnb", "signal": "contract_win"},
        {**base, "url": "u8", "company_text": "Nimbus Clinics", "signal": "award_party"},
        {**base, "url": "u9", "company_text": "Ghost Co Pte Ltd", "signal": "contract_win",
         "snapshot": f"raw/signals/{TODAY}/selftest/missing.md"},
        {**base, "url": "u10", "market": "MY", "company_text": "Bluefin Bistro", "reg_id": "201215175K",
         "signal": "new_branch_opened"},
        {**base, "url": "u11", "kind": "event", "company_text": "", "event": ev},
        {**base, "url": "u12", "company_text": "Pebble Bay Couriers", "signal": "exhibiting_at_event", "event": ev},
    ]
    items_path = r.root.parent / "items.json"
    mc.write_text(items_path, json.dumps(items))
    sig_path = r.root / "log" / "signals.csv"
    bluefin = r.root / "wiki" / "accounts" / "bluefin-bistro.md"
    before_sig, before_bf = mc.read_text(sig_path), mc.read_page(bluefin, r.root)

    code, out, err = r.py("resolve.py", str(items_path), "--run", "t1", "--attach", email=MEI)
    r.record("resolve: rep is refused -> 1", code == 1, f"exit {code}", out + err)

    code, out, err = r.py("resolve.py", str(items_path), "--run", "t1", "--dry-run", "--json", email=MEI)
    d = _json(out)
    st = {x["url"]: (x["status"], x["account"]) for x in d.get("results", [])}
    s = lambda url: st.get(url, ("?", ""))  # noqa: E731
    ok = code == 0 and mc.read_text(sig_path) == before_sig \
        and s("u1") == ("linked", "bluefin-bistro") and s("u2") == ("linked", "copperleaf-retail") \
        and s("u3") == ("linked", "dovetail-movers") and s("u4")[0] == "review" \
        and s("u5")[0] != "linked" and s("u6")[0] == "new_lead" and s("u7")[0] == "dropped" \
        and s("u8")[0] == "dropped" and s("u9")[0] == "rejected"
    r.record("resolve: id / domain / name link, group -> review, conflict, ICP, rejects", ok, f"exit {code}",
             out + err)
    r.record("resolve: never links across markets", s("u10")[0] != "linked" and s("u10")[1] != "bluefin-bistro",
             str(s("u10")))

    code, out, err = r.py("resolve.py", str(items_path), "--run", "t1", "--attach", "--json", email=GRACE)
    d = _json(out)
    rows = mc.read_csv(sig_path)
    new_rows = [x for x in rows if x.get("run") == "t1"]
    review = [x for x in mc.read_csv(r.root / "log" / "review.csv") if x.get("company_text") == "Copperleaf Group"]
    ok = code == 0 and len(new_rows) == 11 and len(review) == 1 \
        and all(x["status"] in ("linked", "review", "new_lead", "dropped", "rejected") for x in new_rows)
    r.record("resolve: every outcome in log/signals.csv, review row written", ok,
             f"exit {code}, {len(new_rows)} rows, {len(review)} review", out + err)

    bf = mc.read_page(bluefin, r.root)
    ok = "new_branch_opened" in bf.meta.get("signals", []) and f"[source]({snap})" in mc.section(bf.body, "Signals") \
        and all(bf.meta.get(k) == before_bf.meta.get(k) for k in ("owner", "stage", "next_action", "tier"))
    r.record("resolve: --attach adds cited bullet + signals:, nothing else", ok)

    lead = r.root / "wiki" / "accounts" / "kopi-corner.md"
    lp = mc.read_page(lead, r.root) if lead.is_file() else None
    ok = lp is not None and lp.meta.get("stage") == "new" and not lp.meta.get("owner") \
        and lp.meta.get("source") == "selftest" and lp.meta.get("signals") == ["new_branch_opened"]
    r.record("resolve: new lead page (stage new, no owner, cited)", ok)

    evp = r.root / "wiki" / "events" / "selftest-expo-2026.md"
    ep = mc.read_page(evp, r.root) if evp.is_file() else None
    ok = ep is not None and ep.meta.get("matched_accounts") == ["pebble-bay-couriers"] \
        and "[[accounts/pebble-bay-couriers]]" in ep.body
    r.record("resolve: event page with matched exhibitor", ok)

    log = mc.read_text(r.root / "wiki" / "log.md")
    r.record("resolve: resolve + unmapped lines logged",
             "resolve | grace | run t1 |" in log and "unmapped | grace |" in log and "award_party" in log)

    code, out, err = r.py("resolve.py", str(items_path), "--run", "t2", "--attach", "--json", email=GRACE)
    d = _json(out)
    ok = code == 0 and not [x for x in mc.read_csv(sig_path) if x.get("run") == "t2"] \
        and d.get("attached", {}).get("signals_attached") == 0
    r.record("resolve: re-run is idempotent (items seen)", ok, f"exit {code}", out + err)

    labelled = r.root.parent / "labelled.csv"
    mc.write_text(labelled, "id,market,source,company_text,expected_account,reg_id,domain,city,note\n"
                            "1,SG,t,Bluefin Bistro,bluefin-bistro,201215175K,,,\n"
                            "2,SG,t,Dovetail Movers Pte. Ltd.,dovetail-movers,,,,\n"
                            "3,SG,t,Copperleaf Group,copperleaf-retail,,,,\n"
                            "4,SG,t,Northwind Coffee,new,,,,\n"
                            "5,SG,t,Pebble Bay Couriers,reject,,,,\n"
                            "6,SG,t,Umbra Legal LLP,reject,,,,\n")
    code, out, err = r.py("resolve.py", "--eval", str(labelled), "--json")
    sg = _json(out).get("SG", {})
    ok = code == 0 and sg.get("auto_linked") == 3 and sg.get("correct_links") == 2 \
        and sg.get("precision") == 0.667 and sg.get("review") == 2 and len(sg.get("wrong", [])) == 1
    r.record("resolve: --eval precision (auto-links only; LLP != Pte Ltd)", ok, f"exit {code}", out + err)

    code, out, err = r.py("lint.py")
    r.record("lint: clean after resolve --attach", code == 0, f"exit {code}", out + err)


def t_score(r: Runner) -> None:
    hl = r.root / "wiki" / "accounts" / "harbourlight-foods.md"
    before = mc.read_page(hl, r.root)
    runs = [r.py("score.py", "--dry-run", "--json", email=GRACE) for _ in range(2)]
    a, b = _json(runs[0][1]), _json(runs[1][1])
    ok = runs[0][0] == 0 and a.get("results") and a.get("results") == b.get("results") \
        and mc.read_text(hl) == before.text \
        and all(set(x["score_parts"]) == {"fit", "intent", "propensity", "engagement"} for x in a["results"])
    r.record("score: dry run is deterministic and writes nothing", ok, f"exit {runs[0][0]}", runs[0][1] + runs[0][2])

    others = [p.id for p in mc.iter_pages("account", r.root) if mc.norm(p.meta.get("owner")) not in ("", "mei")]
    code, out, err = r.py("score.py", "--id", others[0], email=MEI) if others else (0, "", "")
    r.record("score: rep can't score another rep's account -> 1", bool(others) and code == 1, f"exit {code}", out + err)

    code, out, err = r.py("score.py", "--json", email=GRACE)
    after = mc.read_page(hl, r.root)
    m = after.meta
    ok = code == 0 and m.get("tier") in mc.TIERS and isinstance(m.get("score"), float) \
        and str(m.get("score_updated")) == TODAY and after.body == before.body \
        and all(m.get(k) == before.meta.get(k) for k in ("owner", "stage", "updated", "next_action"))
    r.record("score: writes score fields only", ok, f"exit {code}", out + err)
    log = mc.read_text(r.root / "wiki" / "log.md")
    r.record("score: tier mix logged", "score | grace |" in log)

    mc.update_frontmatter(hl, {"score": 0.05, "risk": []})
    code, out, err = r.py("score.py", "--id", "harbourlight-foods", email=MEI)
    m = mc.read_page(hl, r.root).meta
    r.record("score: owner rescoring + hot flag on a jump", code == 0 and "hot" in mc.as_list(m.get("risk")),
             f"exit {code}, risk {m.get('risk')}", out + err)
    mc.update_frontmatter(hl, {"risk": before.meta.get("risk") or []})


def t_recommend(r: Runner) -> None:
    snap = f"raw/research/rec-test/{TODAY}-site.md"
    mc.write_text(r.root / snap, "# rec-test fixture\n")
    meta = {"type": "account", "id": "rec-test", "name": "Rec Test Pte Ltd", "market": "SG", "stage": "new",
            "industry": "retail", "employees": 50, "products_owned": ["managed-wifi"], "recommended": []}
    path = r.root / "wiki" / "accounts" / "rec-test.md"

    def run(signals: list[str], **over) -> dict:
        body = "# Rec Test\n## Snapshot\n## Signals\n" + "".join(
            f"- {s} — [source]({snap})\n" for s in signals) + "## Pains & hypotheses\n"
        mc.write_page(path, {**meta, **over}, body)
        code, out, _ = r.py("recommend.py", "rec-test", "--json", email=GRACE)
        return _json(out) if code == 0 else {}

    def top(d: dict) -> list[str]:
        return [c["product"] for c in d.get("candidates", [])]

    try:
        d = run(["new_branch_opened — second outlet (2026-10-30)", "contract_win — tender (2026-10-29)",
                 "office_move — old move (2026-03-01)"])
        excl = {e["product"]: e["reason"] for e in d.get("excluded", [])}
        ok = top(d) == ["cloud-phone", "it-care"] and excl.get("managed-wifi") == "already owned" \
            and any("office_move" in s for s in d.get("skipped_signals", [])) \
            and all(ch["source"] == snap for c in d["candidates"] for ch in c["chain"])
        r.record("recommend: rank by pains, skip owned, ignore stale signals", ok, str(top(d)))
        d = run(["funding_round — seed round (2026-10-30)"], products_owned=[])
        r.record("recommend: ties -> typical value, then id", top(d) == ["cloud-phone", "it-care"], str(top(d)))
        d = run(["new_branch_opened — second outlet (2026-10-30)"], employees=320)
        r.record("recommend: outside fits.employees -> no fit", top(d) == [] and "320 staff" in d.get("reason", ""),
                 d.get("reason", ""))
        onto = r.root / "knowledge" / "ontology.yaml"  # the demo ontology has no negative term
        onto_orig = mc.read_text(onto)
        mc.write_text(onto, onto_orig.replace("signals:\n", "signals:\n  layoffs_or_closure: "
                                                          "{negative: true, weight: -0.6, decay_days: 180}\n", 1))
        try:
            d = run(["new_branch_opened — outlet (2026-10-30)", "layoffs_or_closure — closing (2026-10-31)"])
        finally:
            mc.write_text(onto, onto_orig)
        r.record("recommend: active negative signal -> no fit", top(d) == [] and "negative" in d.get("reason", ""),
                 d.get("reason", ""))
        d = run(["new_branch_opened — outlet (2026-10-30)"])
        mc.write_text(path, mc.read_text(path).replace(f"[source]({snap})", "[source](raw/research/rec-test/nope.md)"))
        code, out, _ = r.py("recommend.py", "rec-test", "--json", email=GRACE)
        r.record("recommend: uncited signal is ignored", code == 0 and top(_json(out)) == [], out[-200:])
    finally:
        if path.exists():
            path.unlink()


def t_eval(r: Runner) -> None:
    code, out, err = r.py("eval.py", "--json")
    d = _json(out)
    status = {c["key"]: c["status"] for c in d.get("checks", [])}
    ok = code == 0 and d.get("failed") == 0 and status.get("cited") == "PASS" \
        and status.get("suppression") == "PASS" and status.get("golden") == "PASS" \
        and status.get("resolution") in ("PASS", "PENDING") and status.get("recommendation") == "PENDING"
    r.record("eval: demo passes, later phases pending", ok, f"exit {code}", out + err)

    acc = r.root / "wiki" / "accounts" / "copperleaf-retail.md"
    touches = r.root / "log" / "touches.csv"
    acc_orig, touches_orig = mc.read_text(acc), mc.read_text(touches)
    mc.write_text(acc, acc_orig.replace(
        "## Pains & hypotheses", "- new_branch_opened — heard it somewhere\n## Pains & hypotheses", 1))
    with open(touches, "a", encoding="utf-8", newline="") as fh:
        fh.write("2026-11-03 10:30,mei,harbourlight-foods,optout@quietharbour.example,email,fu2,,,"
                 "drafted,,\n")
    try:
        code, out, err = r.py("eval.py", "--json")
        d = _json(out)
        status = {c["key"]: c["status"] for c in d.get("checks", [])}
        ok = code == 1 and status.get("cited") == "FAIL" and status.get("suppression") == "FAIL"
        r.record("eval: unsourced signal + suppressed draft -> 1", ok, f"exit {code}", out + err)
    finally:
        mc.write_text(acc, acc_orig)
        mc.write_text(touches, touches_orig)

    # Golden recommendation: plant one golden account, then break the page's `recommended`.
    sys.path.insert(0, str(r.root / "scripts"))
    import recommend as rc
    hl = r.root / "wiki" / "accounts" / "harbourlight-foods.md"
    hl_orig = mc.read_text(hl)
    golden = r.root / "evals" / "golden_accounts" / "harbourlight-foods.md"
    prev_today = os.environ.get("MAMA_TODAY")
    os.environ["MAMA_TODAY"] = TODAY
    try:
        best = rc.recommend(r.root, "harbourlight-foods")["candidates"][0]["product"]
    finally:
        if prev_today is None:
            os.environ.pop("MAMA_TODAY", None)
        else:
            os.environ["MAMA_TODAY"] = prev_today
    mc.write_text(golden, "---\ntype: account\nid: harbourlight-foods\nmarket: SG\n---\n# golden\n"
                          f"## Expected\n### Recommendation\n- {best} — test\n### Must not\n- text: \"Ghost Person\"\n")
    try:
        mc.update_frontmatter(hl, {"recommended": [best]})
        code, out, err = r.py("eval.py", "--json")
        st = {c["key"]: c for c in _json(out).get("checks", [])}
        ok = st.get("recommendation", {}).get("status") == "PASS" and st.get("entities", {}).get("status") == "PASS"
        r.record("eval: golden recommendation + entities pass", ok, str({k: st.get(k, {}).get("value")
                                                                         for k in ("recommendation", "entities")}),
                 out + err)
        mc.update_frontmatter(hl, {"recommended": ["managed-wifi" if best != "managed-wifi" else "it-care"]})
        mc.write_text(hl, mc.read_text(hl).replace("## Call brief", "## Call brief\nGhost Person said hi.", 1))
        code, out, err = r.py("eval.py", "--json")
        st = {c["key"]: c["status"] for c in _json(out).get("checks", [])}
        r.record("eval: wrong recommendation + must-not name -> 1",
                 code == 1 and st.get("recommendation") == "FAIL" and st.get("entities") == "FAIL", str(st), out + err)
    finally:
        mc.write_text(hl, hl_orig)
        golden.unlink()


PATTERN_OK = """---
type: pattern
id: first-test
step: first
personas: [owner_md]
pains: [branch_expansion]
signals: [new_branch_opened]
markets: [SG]
lang: en
status: approved
updated: 2026-11-03
---
# first-test
## Structure
## Example (fictional company)
## Rules
"""
DRAFT_OK = ("Hi Rachel,\n\nI saw Harbourlight Foods has a second kitchen opening in Tampines. IT Care covers "
            "helpdesk, device setup and backups for both kitchens.\n\nWorth a 15-minute call?\n\nMei Chen\n"
            "Account Executive, Example Co (fictional)\n\nReply \"unsubscribe\" and I won't email you again.\n")


def t_draft_check(r: Runner) -> None:
    hl = r.root / "wiki" / "accounts" / "harbourlight-foods.md"
    sup = r.root / "wiki" / "suppression.csv"
    hl_orig, sup_orig = mc.read_text(hl), mc.read_text(sup)
    mc.write_text(r.root / "wiki" / "responses" / "patterns" / "first-test.md", PATTERN_OK)
    draft = r.root / "draft.txt"
    mc.write_text(draft, DRAFT_OK)
    base = ["--account", "harbourlight-foods", "--contact", "rachel-goh-harbourlight-foods", "--step", "first",
            "--pattern", "first-test", "--products", "it-care", "--subject", "Your Tampines kitchen",
            "--file", str(draft)]

    def failed(code_out) -> list[str]:
        d = _json(code_out[1])
        return [c["check"] for c in d.get("checks", []) if not c["ok"]]

    try:
        mc.update_frontmatter(hl, {"stage": "researched", "recommended": ["it-care"]})
        res = r.py("draft_check.py", *base, "--save", email=MEI)
        d = _json(res[1])
        r.record("draft_check: clean first email passes + saved", res[0] == 0 and d.get("ok")
                 and str(d.get("saved", "")).startswith("log/drafts/"), str(failed(res)), res[1] + res[2])
        res = r.py("draft_check.py", *base, email=ARUN)
        r.record("draft_check: not the owner -> owner fails", res[0] == 1 and "owner" in failed(res), str(failed(res)))
        mc.write_text(draft, DRAFT_OK.replace("in Tampines", "in Jurong with Acme Bank"))
        res = r.py("draft_check.py", *base, email=MEI)
        r.record("draft_check: fabricated name -> entities fails", res[0] == 1 and failed(res) == ["entities"],
                 str(failed(res)))
        mc.write_text(draft, DRAFT_OK)
        with open(sup, "a", encoding="utf-8", newline="") as fh:
            fh.write("harbourlightfoods.example,domain,unsubscribe,grace,2026-11-01\n")
        res = r.py("draft_check.py", *base, email=MEI)
        r.record("draft_check: suppressed domain -> suppression fails", res[0] == 1 and "suppression" in failed(res),
                 str(failed(res)))
        mc.write_text(sup, sup_orig)
        mc.update_frontmatter(hl, {"signals": ["contract_ending", "new_branch_opened"], "contract_end": "2027-06-01"})
        res = r.py("draft_check.py", *base, email=MEI)
        r.record("draft_check: contract_ending too early -> contract_timing fails",
                 res[0] == 1 and failed(res) == ["contract_timing"], str(failed(res)))
        code, out, _ = r.py("draft_check.py", "--next-window", "--market", "SG", email=MEI)
        r.record("draft_check: next send window is a SG weekday slot",
                 code == 0 and _json(out).get("date") == TODAY and "SGT" in _json(out).get("label", ""), out)
        mc.write_text(hl, hl_orig)
        code, out, err = r.py("eval.py", "--json")
        st = {c["key"]: c["status"] for c in _json(out).get("checks", [])}
        ok = all(st.get(k) == "PASS" for k in ("send_window", "language", "draft_catalog", "fabrication"))
        r.record("eval: saved draft passes the Phase 4 draft checks", ok, str(st), out + err)
        saved = next((r.root / "log" / "drafts").glob("*.md"))
        mc.write_text(saved, mc.read_text(saved).replace("in Tampines", "in Jurong"))
        code, out, err = r.py("eval.py", "--json")
        st = {c["key"]: c["status"] for c in _json(out).get("checks", [])}
        r.record("eval: fabricated name in a saved draft -> 1", code == 1 and st.get("fabrication") == "FAIL", str(st))
    finally:
        mc.write_text(hl, hl_orig)
        mc.write_text(sup, sup_orig)
        for f in (r.root / "log" / "drafts").glob("*.md"):
            f.unlink()
        draft.unlink()


WA_SRC = "raw/research/harbourlight-foods/2026-10-20-site.md"


def t_send(r: Runner) -> None:
    """send.py approve-then-send on the fake transport (ADR-0007)."""
    root = r.root
    hl = root / "wiki" / "accounts" / "harbourlight-foods.md"
    con = root / "wiki" / "contacts" / "rachel-goh-harbourlight-foods.md"
    keep = [hl, con, root / "wiki" / "suppression.csv", root / "log" / "touches.csv", root / "reps" / "mei.md",
            root / "knowledge" / "sending.yaml", root / "wiki" / "log.md"]
    orig = {p: mc.read_text(p) for p in keep if p.is_file()}
    cfg_dir = root.parent / "mama-config"
    mc.write_text(root / "wiki" / "responses" / "patterns" / "first-test.md", PATTERN_OK)
    draft = root / "draft.txt"

    def sp(script: str, *args: str, email: str = MEI, now: str = "2026-11-03 10:00", **extra) -> tuple[int, str]:
        env = r.env(email, MAMA_SEND_TRANSPORT="fake", MAMA_NOW=now, MAMA_CONFIG_DIR=str(cfg_dir), **extra)
        proc = subprocess.run([sys.executable, str(root / "scripts" / script), *args], cwd=str(root),
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=300)
        return proc.returncode, proc.stdout + proc.stderr

    def preview(**kw) -> dict:
        return _json(sp("send.py", "--preview", "--json", **kw)[1])

    def send(pid: str, items: str = "all", **kw) -> tuple[int, dict]:
        code, out = sp("send.py", "--send", pid, "--items", items, "--json", **kw)
        return code, _json(out)

    def problems(p: dict) -> str:
        return " ".join(" ".join(i.get("problems", [])) for i in p.get("items", []))

    def save_email() -> None:
        mc.write_text(draft, DRAFT_OK)
        code, out = sp("draft_check.py", "--account", "harbourlight-foods", "--contact",
                       "rachel-goh-harbourlight-foods", "--step", "first", "--pattern", "first-test", "--products",
                       "it-care", "--subject", "Your Tampines kitchen", "--file", str(draft), "--save")
        if code != 0:
            raise RuntimeError(f"draft_check failed: {out[:500]}")

    def clean_touches() -> None:  # Harbourlight starts with no touches, so `first` is unsent
        lines = orig[root / "log" / "touches.csv"].splitlines(keepends=True)
        mc.write_text(root / "log" / "touches.csv", "".join(ln for ln in lines if "harbourlight-foods" not in ln))

    def reset() -> None:
        for p_, t in orig.items():
            mc.write_text(p_, t)
        clean_touches()
        mc.update_frontmatter(hl, {"stage": "researched", "recommended": ["it-care"]})
        for folder in ("drafts", "outbox"):
            for f in (root / "log" / folder).glob("*"):
                if f.name != ".gitkeep":
                    f.unlink()
        (root / "log" / "approvals.csv").unlink(missing_ok=True)

    def enable(on: bool = True) -> None:
        mc.write_text(root / "knowledge" / "sending.yaml", f"enabled: {'true' if on else 'false'}\n"
                      "channels: {email: true, whatsapp: true}\nmax_per_run: 25\n")

    try:
        reset()
        save_email()
        enable(False)
        p = preview()
        ready = bool(p.get("items")) and p["items"][0].get("ok")
        code, d = send(p.get("id", "x"))
        r.record("send: preview shows a READY item; send refused while sending is off",
                 ready and code == 1 and "switched off" in d.get("error", ""), str(d) + problems(p))
        enable()
        code, d = send(p["id"], MAMA_RUNNER="1")
        r.record("send: the nightly runner is refused", code == 1 and "runner" in d.get("error", ""), str(d))
        code, d = send(p["id"], email=ARUN)
        r.record("send: another rep cannot use mei's preview", code == 1 and "belongs to mei" in d.get("error", ""),
                 str(d))
        r.record("send: outside the window -> window_now blocks",
                 "window_now" in problems(preview(now="2026-11-03 12:00")), problems(preview(now="2026-11-03 12:00")))
        r.record("send: public holiday -> window_now blocks",
                 "holiday" in problems(preview(now="2026-11-09 10:00")), problems(preview(now="2026-11-09 10:00")))
        with open(root / "wiki" / "suppression.csv", "a", encoding="utf-8", newline="") as fh:
            fh.write("harbourlightfoods.example,domain,unsubscribe,grace,2026-11-01\n")
        r.record("send: suppressed domain -> suppression blocks", "suppression" in problems(preview()))
        mc.write_text(root / "wiki" / "suppression.csv", orig[root / "wiki" / "suppression.csv"])
        mc.update_frontmatter(root / "reps" / "mei.md", {"daily_quota": 0})
        p = preview()
        code, d = send(p["id"])
        r.record("send: over the daily quota -> refused", code == 1 and "quota" in d.get("error", ""), str(d))
        mc.write_text(root / "reps" / "mei.md", orig[root / "reps" / "mei.md"])
        p = preview()
        saved = next((root / "log" / "drafts").glob("*.md"))
        before = mc.read_text(saved)
        mc.write_text(saved, before.replace("Worth a 15-minute call?", "Worth a quick call?"))
        code, d = send(p["id"])
        r.record("send: draft changed after the preview -> refused",
                 code == 1 and "changed since the preview" in json.dumps(d), str(d))
        mc.write_text(saved, before)

        p = preview()
        code, d = send(p["id"], "1")
        res = (d.get("results") or [{}])[0]
        appr = mc.read_csv(root / "log" / "approvals.csv")
        sent = [t for t in mc.load_touches(root) if t.get("status") == "sent" and t.get("ref", "").startswith("gmail:")]
        acc = mc.read_page(hl, root)
        ok = code == 0 and res.get("status") == "sent" and str(res.get("ref", "")).startswith("gmail:") \
            and [a["decision"] for a in appr].count("sent") == 1 and "refused" in [a["decision"] for a in appr] \
            and len(sent) == 1 and sent[0]["ref"] == res["ref"] \
            and acc.meta.get("stage") == "contacted" and res["ref"] in acc.body \
            and mc.read_page(saved, root).meta.get("sent_ref") == res["ref"]
        r.record("send: approved email -> one approval, one sent touch, stage contacted", ok,
                 f"{d} decisions={[a['decision'] for a in appr]} sent={len(sent)} "
                 f"stage={acc.meta.get('stage')} in_body={res.get('ref', '?') in acc.body}")
        code, d = send(p["id"], "1")
        r.record("send: same item twice -> refused (already sent)", code == 1 and "already sent" in json.dumps(d), str(d))
        code, out, err = r.py("eval.py", "--json")
        st = {c["key"]: c["status"] for c in _json(out).get("checks", [])}
        r.record("eval: approved send passes the send checks",
                 all(st.get(k) == "PASS" for k in ("send_approval", "send_window_sent", "send_suppressed")), str(st))
        with open(root / "log" / "touches.csv", "a", encoding="utf-8", newline="") as fh:
            fh.write("2026-11-03 10:05,mei,harbourlight-foods,rachel-goh-harbourlight-foods,email,fu1,first-test,,"
                     "sent,,gmail:not-approved\n")
        code, out, err = r.py("eval.py", "--json")
        st = {c["key"]: c["status"] for c in _json(out).get("checks", [])}
        r.record("eval: a script send without an approval -> send_approval FAIL", code == 1
                 and st.get("send_approval") == "FAIL", str(st))

        # WhatsApp
        reset()
        enable()
        wa = ["--account", "harbourlight-foods", "--contact", "rachel-goh-harbourlight-foods", "--step", "first",
              "--channel", "whatsapp", "--pattern", "first-test", "--products", "it-care"]
        tpl = ["--wa-template", "first-new-branch-wa", "--wa-params", "Rachel|Tampines kitchen"]
        mc.update_frontmatter(con, {"whatsapp": "+6591234567", "whatsapp_opt_in": True})
        code, out = sp("draft_check.py", *wa, *tpl)
        fails = [c["check"] for c in _json(out).get("checks", []) if not c["ok"]]
        r.record("draft_check: WhatsApp without consent date and source -> consent fails",
                 code == 1 and fails == ["consent"], str(fails))
        mc.update_frontmatter(con, {"whatsapp_opt_in_date": "2026-10-30", "whatsapp_opt_in_source": WA_SRC})
        mc.write_text(draft, "Hi Rachel, quick question about your Tampines kitchen. Reply STOP to opt out.\n")
        with open(root / "log" / "touches.csv", "a", encoding="utf-8", newline="") as fh:
            fh.write("2026-11-01 09:00,mei,harbourlight-foods,rachel-goh-harbourlight-foods,whatsapp,reply,,,"
                     "replied,interested,raw/replies/x.md\n")
        code, out = sp("draft_check.py", *wa, "--file", str(draft))
        fails = [c["check"] for c in _json(out).get("checks", []) if not c["ok"]]
        r.record("draft_check: WhatsApp free text after the 24 h window -> template fails",
                 code == 1 and "template" in fails, str(fails))
        clean_touches()
        code, out = sp("draft_check.py", *wa, "--wa-template", "first-office-move-wa", "--wa-params",
                       "Rachel|Harbourlight Foods")
        fails = [c["check"] for c in _json(out).get("checks", []) if not c["ok"]]
        r.record("draft_check: WhatsApp template stating a signal the account lacks -> template fails",
                 code == 1 and fails == ["template"], str(fails))
        code, out = sp("draft_check.py", *wa, *tpl, "--save")
        d = _json(out)
        r.record("draft_check: WhatsApp template with consent passes + saved",
                 code == 0 and "new Tampines kitchen" in d.get("body", "") and d.get("saved"), out[:600])
        p = preview()
        code, d = send(p.get("id", "x"))
        res = (d.get("results") or [{}])[0]
        code2, out2, _ = r.py("eval.py", "--json")
        st = {c["key"]: c["status"] for c in _json(out2).get("checks", [])}
        r.record("send: approved WhatsApp template -> wa: ref, consent eval passes",
                 code == 0 and str(res.get("ref", "")).startswith("wa:wamid.") and st.get("send_consent") == "PASS",
                 str(d) + str(st) + problems(p))
    finally:
        reset()
        mc.write_text(root / "log" / "touches.csv", orig[root / "log" / "touches.csv"])
        (root / "wiki" / "responses" / "patterns" / "first-test.md").unlink(missing_ok=True)
        draft.unlink(missing_ok=True)


def t_classify(r: Runner) -> None:
    cases = {"Please remove me from your mailing list.": "unsubscribe",
             "Delivery Status Notification (Failure): address not found": "bounce",
             "I am out of the office until 10 Nov with limited access to email.": "out_of_office",
             "Could we do Thursday 10am? Send me an invite.": "meeting_request",
             "We already have a provider and are happy with them.": "objection",
             "Not now, maybe check back next quarter.": "not_now",
             "Sounds interesting, can you send more details?": "interested",
             "I'm not the right person, please contact our IT manager.": "wrong_person",
             "Thanks, nothing to add.": "not_now"}
    bad = []
    for text, want in cases.items():
        code, out, _ = r.py("classify_reply.py", "--text", text)
        got = _json(out).get("class")
        if got != want:
            bad.append(f"{want}->{got}")
    r.record("classify_reply: one case per class + cautious default", not bad, ", ".join(bad))
    csv_path = r.root / "evals" / "labeled_replies.csv"
    orig = mc.read_text(csv_path)
    rows = "".join(f"t{i},SG,en,\"{t}\",{c}\n" for i, (t, c) in enumerate(list(cases.items()) * 5))
    mc.write_text(csv_path, "id,market,lang,text,label\n" + rows)
    try:
        code, out, err = r.py("eval.py", "--json")
        st = {c["key"]: c for c in _json(out).get("checks", [])}
        r.record("eval: replies row live at 40+ rows", st.get("replies", {}).get("status") == "PASS",
                 str(st.get("replies")), out + err)
    finally:
        mc.write_text(csv_path, orig)


def t_suppress(r: Runner) -> None:
    con = r.root / "wiki" / "contacts" / "rachel-goh-harbourlight-foods.md"
    hl = r.root / "wiki" / "accounts" / "harbourlight-foods.md"
    sup = r.root / "wiki" / "suppression.csv"
    orig = {p: mc.read_text(p) for p in (con, hl, sup)}
    try:
        code, out, err = r.py("suppress.py", "--email", "Rachel@HarbourlightFoods.example", email=MEI)
        d = _json(out)
        rows = [x for x in mc.read_csv(sup) if x["value"] == "rachel@harbourlightfoods.example"]
        ok = code == 0 and d.get("added") and len(rows) == 1 and rows[0]["added_by"] == "mei" \
            and mc.read_page(con, r.root).meta.get("status") == "do_not_contact" \
            and mc.read_page(hl, r.root).meta.get("stage") == "do_not_contact"
        r.record("suppress: unsubscribe -> csv row, contact + account stopped", ok, str(d), out + err)
        code, out, _ = r.py("suppress.py", "--email", "rachel@harbourlightfoods.example", email=MEI)
        rows = [x for x in mc.read_csv(sup) if x["value"] == "rachel@harbourlightfoods.example"]
        r.record("suppress: idempotent", code == 0 and not _json(out).get("added") and len(rows) == 1)
        mc.write_text(r.root / "draft.txt", DRAFT_OK)
        mc.write_text(hl, orig[hl])
        code, out, _ = r.py("draft_check.py", "--account", "harbourlight-foods", "--contact",
                            "rachel-goh-harbourlight-foods", "--step", "reply", "--file", str(r.root / "draft.txt"),
                            email=MEI)
        fails = [c["check"] for c in _json(out).get("checks", []) if not c["ok"]]
        r.record("suppress: draft to the unsubscribed contact is refused", code == 1 and "suppression" in fails
                 and "status" in fails, str(fails))
    finally:
        for p, t in orig.items():
            mc.write_text(p, t)
        (r.root / "draft.txt").unlink(missing_ok=True)


def _pool_page(acc: str, **over) -> tuple[dict, str]:
    meta = {"type": "account", "id": acc, "name": acc.replace("-", " ").title(), "market": "SG",
            "domain": f"{acc}.example", "group": None, "owner": None, "allocated_on": None,
            "allocated_by": None, "claimed_on": None, "stage": "new", "industry": "fnb",
            "employees": 30, "region": "east", "score": 0.4, "tier": "C", "updated": "2026-11-01"}
    meta.update(over)
    return meta, f"# {meta['name']}\n## Snapshot\n## Signals\n## VAM notes\n"


def _team_repo(r: Runner) -> tuple[Runner, Runner, Path]:
    """A pushed seed repo with extra pool fixtures + a bare remote and two clones
    (mei, grace). Built once and shared by t_claim, t_allocate and t_claim_race."""
    if getattr(r, "_team", None):
        return r._team  # type: ignore[attr-defined]
    base = r.root.parent / "team"
    seed = base / "seed"
    setup(mc.repo_root(), seed)
    acc = seed / "wiki" / "accounts"
    fixtures = {f"pool-c-{i}": {} for i in range(1, 5)}
    fixtures.update({
        "pool-a-1": {"tier": "A", "score": 0.8},
        "pool-my-c": {"market": "MY", "region": "selangor"},
        "pool-supp": {"domain": "quietsupp.example"},
        "pool-west": {"region": "west"},
        "pool-dnc": {"stage": "do_not_contact"},
        "kopi-sister": {"tier": "B", "score": 0.6, "group": "Harbour Group"},
    })
    fixtures.update({f"race-{k}-{i}": {} for k in range(1, 5) for i in range(1, 4)})
    for a, over in fixtures.items():
        meta, body = _pool_page(a, **over)
        mc.write_page(acc / f"{a}.md", meta, body)
    mc.update_frontmatter(acc / "harbourlight-foods.md", {"group": "Harbour Group"})
    with open(seed / "wiki" / "suppression.csv", "a", encoding="utf-8", newline="") as fh:
        fh.write("quietsupp.example,domain,unsubscribe,grace,2026-11-01\n")
    for p in (seed / "log" / "allocation").glob("*"):
        p.unlink()
    mc.run_git(["add", "-A"], cwd=seed)
    mc.run_git(["commit", "-qm", "seed"], cwd=seed)
    remote = base / "remote.git"
    remote.mkdir(parents=True)
    git_init(remote, bare=True)
    mc.run_git(["remote", "add", "origin", str(remote)], cwd=seed)
    mc.run_git(["push", "-qu", "origin", "main"], cwd=seed)
    clones = []
    for who, email in (("mei", MEI), ("grace", GRACE)):
        path = base / who
        mc.run_git(["clone", "-q", str(remote), str(path)], cwd=base)
        for k, v in (("user.name", who), ("user.email", email), ("commit.gpgsign", "false"),
                     ("core.autocrlf", "false"), ("pull.rebase", "true")):
            mc.run_git(["config", k, v], cwd=path)
        clones.append(Runner(path, r.verbose))
    r._team = (clones[0], clones[1], remote)  # type: ignore[attr-defined]
    return r._team  # type: ignore[attr-defined]


def _owner(rr: Runner, acc: str) -> dict:
    page = mc.read_page(rr.root / "wiki" / "accounts" / f"{acc}.md", rr.root)
    return (page.meta if page else None) or {}


def t_claim(r: Runner) -> None:
    mei, grace, remote = _team_repo(r)
    ok_all = True

    def run(rr, email, *args):
        code, out, err = rr.py("claim.py", *args, "--json", email=email)
        return code, _json(out), out + err

    code, d, out = run(mei, MEI, "pool-c-1")
    m = _owner(mei, "pool-c-1")
    _, rlog, _ = r.git("log", "-1", "--format=%s", "main", cwd=remote)
    ok = code == 0 and m.get("owner") == "mei" and str(m.get("claimed_on")) == TODAY \
        and d.get("pushed") is True and "claim pool-c-1" in rlog
    ok_all &= r.record("claim: self-claim tier C, pushed", ok, f"exit {code}", out)
    for acc, expect, label in (("pool-a-1", "tier A", "tier A refused"),
                               ("pool-my-c", "not live", "non-live market refused"),
                               ("pool-supp", "suppressed", "suppressed domain refused"),
                               ("pool-west", "region west", "outside territory refused"),
                               ("pool-dnc", "do_not_contact", "do_not_contact refused")):
        code, d, out = run(mei, MEI, acc)
        rej = (d.get("rejected") or [{}])[0].get("reason", "")
        r.record(f"claim: {label}", code == 2 and expect in rej and not _owner(mei, acc).get("owner"),
                 rej[:60], out)
    code, d, out = run(mei, MEI, "--assign", "mei", "pool-c-2")
    r.record("claim: rep cannot --assign", code == 2 and "only the manager" in out, f"exit {code}", out)
    code, d, out = run(grace, GRACE, "pool-c-1")
    r.record("claim: owned account cannot be claimed again",
             code == 2 and "already owned by mei" in out, f"exit {code}", out)
    code, d, out = run(mei, MEI, "--release", "pool-c-1")
    r.record("claim: owner releases", code == 0 and not _owner(mei, "pool-c-1").get("owner"), f"exit {code}", out)
    code, d, out = run(grace, GRACE, "--assign", "mei", "pool-a-1")
    m = _owner(grace, "pool-a-1")
    r.record("claim: manager --assign tier A", code == 0 and m.get("owner") == "mei"
             and m.get("allocated_by") == "grace", f"exit {code}", out)
    code, d, out = run(grace, GRACE, "--reassign", "mei", "arun", "pool-a-1")
    r.record("claim: --reassign refuses a rep outside the market",
             code == 2 and "does not cover SG" in out and _owner(grace, "pool-a-1").get("owner") == "mei",
             f"exit {code}", out)
    code, d, out = run(grace, GRACE, "--reassign", "mei", "grace", "pool-a-1")
    r.record("claim: --reassign to a fitting rep", code == 0 and _owner(grace, "pool-a-1").get("owner") == "grace",
             f"exit {code}", out)
    code, out, err = mei.py("claim.py", "--suggest", "0", "--json", email=MEI)
    try:
        sug = {x["account"] for x in json.loads(out)}
    except Exception:  # noqa: BLE001
        sug = set()
    r.record("claim: --suggest lists only claimable tier C", code == 0 and "pool-c-2" in sug
             and not sug & {"pool-a-1", "pool-my-c", "pool-supp", "pool-west", "pool-dnc", "kopi-sister"},
             f"{len(sug)} suggested", out + err)


def t_claim_race(r: Runner) -> None:
    """Two clones claim the same accounts at the same moment; prove no double claims."""
    mei, grace, remote = _team_repo(r)
    won: dict[str, list[str]] = {}
    lost_ok = True
    for k in range(1, 5):
        accs = [f"race-{k}-{i}" for i in range(1, 4)]
        procs = []
        # Both pass the check before either pushes; who pushes first alternates.
        for rr, email in ((mei, MEI), (grace, GRACE)):
            rr.git("pull", "-q", "--rebase")
            first = (rr is mei) == (k % 2 == 1)
            env = rr.env(email, MAMA_CLAIM_TEST_PAUSE="1.0" if first else "2.0")
            procs.append((rr, subprocess.Popen(
                [sys.executable, str(rr.root / "scripts" / "claim.py"), *accs, "--json"],
                cwd=str(rr.root), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8")))
        for rr, p in procs:
            out, err = p.communicate(timeout=300)
            d = _json(out)
            who = "mei" if rr is mei else "grace"
            for o in d.get("applied") or []:
                won.setdefault(o["account"], []).append(who)
            for x in d.get("rejected") or []:
                lost_ok &= x["reason"].startswith("already owned by")
    # Truth from the remote: one owner each, set by exactly one commit.
    check = r.root.parent / "team" / "check"
    if check.exists():
        _rmtree(check)
    mc.run_git(["clone", "-q", str(remote), str(check)], cwd=r.root.parent)
    doubles, owners, sets = [], {}, {}
    for k in range(1, 5):
        for i in range(1, 4):
            a = f"race-{k}-{i}"
            meta = mc.read_page(check / "wiki" / "accounts" / f"{a}.md", check).meta or {}
            owners[a] = mc.norm(meta.get("owner"))
            _, log, _ = mc.run_git(["log", "-p", "--format=", "--", f"wiki/accounts/{a}.md"], cwd=check)
            sets[a] = sum(1 for ln in log.splitlines() if ln.startswith("+owner: ") and ln[8:].strip())
            if len(won.get(a, [])) != 1 or sets[a] != 1 or not owners[a] or won[a][0] != owners[a]:
                doubles.append(a)
    winners = {w for v in won.values() for w in v}
    r.record("claim race: 12 contested accounts, zero double claims", not doubles and lost_ok,
             f"doubles {doubles}; claims per account {sets}")
    r.record("claim race: both clones won some (race was real)", winners == {"mei", "grace"},
             f"winners {sorted(winners)}")


def t_allocate(r: Runner) -> None:
    mei, grace, remote = _team_repo(r)
    grace.git("pull", "-q", "--rebase")
    code, out, err = grace.py("allocate.py", "--json", email=GRACE)
    d = _json(out)
    rows = d.get("rows") or []
    by = {x["account"]: x for x in rows}
    held = {u["account"]: u["reason"] for u in d.get("unassigned") or []}
    count = {}
    for x in rows:
        count[x["rep"]] = count.get(x["rep"], 0) + 1
    ok = code == 0 and rows and all(c["ok"] for c in d.get("checks") or [{"ok": False}]) \
        and all(x["reason"] for x in rows) \
        and by.get("kopi-sister", {}).get("rep") == "mei" and "same group" in by["kopi-sister"]["reason"] \
        and "pool-my-c" not in by and "not live" in held.get("pool-my-c", "") \
        and "pool-supp" not in by and "pool-dnc" not in by \
        and by.get("pool-west", {}).get("rep") in (None, "grace") \
        and not any(x["rep"] == "arun" for x in rows) and count.get("grace", 0) <= 5 \
        and count.get("mei", 0) <= 15 and (d.get("path") or "").startswith("log/allocation/")
    r.record("allocate: constraints, continuity, quota, reasons", bool(ok),
             f"exit {code}, {len(rows)} rows", out + err)
    code, out, err = mei.py("allocate.py", "--dry-run", email=MEI)
    r.record("allocate: rep is refused", code == 1 and "manager" in out, f"exit {code}", out + err)
    code, out, err = grace.py("allocate.py", "--approve", "all", "--except", "1", "--json", email=GRACE)
    a = _json(out)
    page = mc.read_page(grace.root / d.get("path", "x"), grace.root)
    first = next((x for x in rows if x["row"] == 1), {})
    ok = code == 0 and a.get("status") == "partial" and len(a.get("applied") or []) == len(rows) - 1 \
        and all(_owner(grace, x["account"]).get("owner") == x["rep"] for x in rows if x["row"] != 1) \
        and not _owner(grace, first.get("account", "x")).get("owner") \
        and page is not None and mc.norm(page.meta.get("status")) == "partial" and "## Decisions" in page.body
    r.record("allocate: --approve all --except 1 assigns the rest", bool(ok), f"exit {code}", out + err)
    code, out, err = grace.py("allocate.py", "--approve", "all", email=GRACE)
    r.record("allocate: a decided proposal can't be approved twice", code == 1 and "already" in out,
             f"exit {code}", out + err)


def t_weekly(r: Runner) -> None:
    code, out, err = r.py("weekly.py", "--json", email=GRACE)
    d = _json(out)
    ok = code == 0 and d.get("week") == "2026-W45" and d["calibration"]["verdict"] == "insufficient" \
        and d["metrics"]["week"]["total"]["reply_rate"] == "insufficient data"
    r.record("weekly: demo -> insufficient data, W45", ok, str(d.get("calibration")), out + err)
    acc_dir, touches = r.root / "wiki" / "accounts", r.root / "log" / "touches.csv"
    orig = mc.read_text(touches)
    made = []
    try:
        for tier in ("A", "C"):
            for i in range(20):
                acc = f"cal-{tier.lower()}-{i}"
                meta, body = _pool_page(acc, tier=tier, owner="mei", stage="contacted")
                mc.write_page(acc_dir / f"{acc}.md", meta, body)
                made.append(acc_dir / f"{acc}.md")
                mc.append_csv(touches, {"ts": "2026-11-02 10:00", "rep": "mei", "account": acc, "channel": "email",
                                        "step": "first", "status": "sent"}, mc.TOUCH_FIELDS)
                if i < 4:
                    mc.append_csv(touches, {"ts": "2026-11-03 10:00", "rep": "mei", "account": acc,
                                            "channel": "meeting", "step": "meeting", "status": "meeting_held"},
                                  mc.TOUCH_FIELDS)
        code, out, err = r.py("weekly.py", "--json", "--week", "2026-W45", email=GRACE)
        d = _json(out)
        c = d.get("calibration", {})
        ok = code == 0 and c.get("verdict") == "propose" and (c.get("lift_a_over_c") or 9) < 2 \
            and c["tiers"]["C"] == {"contacted": 20, "meetings": 4, "meeting_rate": 0.2}
        r.record("weekly: tier A < 2x tier C (n>=20) -> propose", ok, str(c), out + err)
        code, out, _ = r.py("weekly.py", "--week", "bad")
        r.record("weekly: bad --week refused", code == 1)
    finally:
        mc.write_text(touches, orig)
        for p in made:
            p.unlink(missing_ok=True)


def t_crm_update(r: Runner) -> None:
    hl = r.root / "wiki" / "accounts" / "harbourlight-foods.md"
    touches = r.root / "log" / "touches.csv"
    crm = r.root / "log" / "crm-updates" / f"{TODAY}.csv"
    orig = {p: mc.read_text(p) for p in (hl, touches)}
    try:
        mc.update_frontmatter(hl, {"stage": "handed_over", "next_action": "Pilot scoping call",
                                   "next_action_due": "2026-11-12"})
        args = ("--id", "harbourlight-foods", "--notes", "2-site pilot, decision by 30 Nov", "--products", "it-care")
        code, out, err = r.py("crm_update.py", *args, email=MEI)
        rows = mc.read_csv(crm)
        header = mc.read_text(crm).splitlines()[0] if crm.is_file() else ""
        ok = code == 0 and header == "Account Name,Stage,Next Step,Owner Email,Notes" and len(rows) == 1 \
            and rows[0]["Stage"] == "handed_over" and rows[0]["Next Step"] == "Pilot scoping call by 2026-11-12" \
            and rows[0]["Owner Email"] == MEI and rows[0]["Notes"] == "2-site pilot, decision by 30 Nov" \
            and mc.load_touches(r.root)[-1]["status"] == "meeting_held"
        r.record("crm_update: mapped header, quoted row, meeting touch", ok, header, out + err)
        code, out, _ = r.py("crm_update.py", *args, email=ARUN)
        r.record("crm_update: another rep's account refused", code == 1 and "Refused" in out
                 and len(mc.read_csv(crm)) == 1, out)
        code, out, _ = r.py("crm_update.py", "--id", "harbourlight-foods", "--notes", "x", "--products", "bogus",
                            email=MEI)
        r.record("crm_update: unknown product refused (rule 4)", code == 1 and "bogus" in out, out)
    finally:
        for p, text in orig.items():
            mc.write_text(p, text)
        crm.unlink(missing_ok=True)


def t_help(r: Runner) -> None:
    bad = []
    for s in ("mama_common.py", "session_start.py", "sync.py", "build_index.py",
              "build_books.py", "find.py", "guard.py", "lint.py", "sync_skills.py",
              "ingest.py", "eval.py", "fetch_dataset.py", "resolve.py", "score.py", "recommend.py",
              "draft_check.py", "classify_reply.py", "suppress.py", "claim.py", "allocate.py",
              "weekly.py", "crm_update.py", "channels.py", "connect.py", "send.py"):
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
        for test in (t_help, t_frontmatter, t_guard, t_lint, t_lint_secrets, t_find, t_index, t_books, t_session,
                     t_sync, t_skills, t_ingest, t_fetch, t_resolve, t_score, t_recommend, t_eval,
                     t_draft_check, t_send, t_classify, t_suppress, t_claim, t_claim_race, t_allocate,
                     t_weekly, t_crm_update):
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
