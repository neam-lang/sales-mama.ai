"""Session start for Sales Mama (Claude Code SessionStart hook, or run by hand).

Steps:
1. `git pull --rebase --autostash` when the branch has an upstream. A failure
   only prints a warning (a conflicting rebase is aborted so the working tree
   is left as it was). No remote or no upstream -> skipped quietly.
2. Rebuild wiki/index.md and wiki/books/ in-process (if those scripts exist).
3. Print a short banner and the current user's queue:
   - rep: due / overdue next actions, hot accounts, at-risk accounts,
     VAM pre-drafts waiting (owned accounts with a non-empty '## VAM notes'
     section), quota left today (daily_quota minus today's drafted/sent touches)
   - manager: allocation proposals pending, review-queue rows without a
     decision, the latest manager brief, plus their own accounts if any
   - unknown user: "Run mama-setup"

ALWAYS exits 0, even on unexpected errors (prints a one-line warning), so a
broken script can never block a session.

    python3 scripts/session_start.py
    python3 scripts/session_start.py --no-pull     # skip git (offline)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

MAX_ITEMS = 5


def _pull(root: Path, mc) -> str | None:
    """Pull if there is an upstream. Returns a warning line or None."""
    code, _, _ = mc.run_git(["rev-parse", "--is-inside-work-tree"], cwd=root, timeout=15)
    if code != 0:
        return None  # not a git repo yet: nothing to pull
    if mc.rebase_in_progress(root) or mc.merge_in_progress(root):
        return ("a git rebase/merge is in progress; skipped pull. Run `python3 scripts/sync.py` "
                "or ask the agent to finish it.")
    if not mc.git_remotes(root) or not mc.git_upstream(root):
        return None
    code, out, err = mc.run_git(["pull", "--rebase", "--autostash", "--quiet"], cwd=root, timeout=60)
    if code == 0:
        return None
    if mc.rebase_in_progress(root):
        mc.run_git(["rebase", "--abort"], cwd=root, timeout=30)
        return ("pull hit a conflict, so it was undone and your files are unchanged. "
                "Run `python3 scripts/sync.py` for next steps.")
    msg = (err or out).strip().splitlines()
    return f"git pull failed ({msg[-1] if msg else f'exit {code}'}); working offline."


def _rebuild(root: Path) -> list[str]:
    warnings: list[str] = []
    here = Path(__file__).resolve().parent
    for name in ("build_index", "build_books"):
        if not (here / f"{name}.py").is_file():
            continue
        try:
            mod = __import__(name)
            mod.build(root)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{name} failed: {type(exc).__name__}: {exc}".splitlines()[0])
    return warnings


def _fmt(items: list[str]) -> str:
    extra = len(items) - MAX_ITEMS
    return ", ".join(items[:MAX_ITEMS]) + (f", +{extra} more" if extra > 0 else "")


def _rep_queue(user: dict, root: Path, mc) -> list[str]:
    on = mc.today()
    mine = [p for p in mc.iter_pages("account", root) if mc.norm(p.meta.get("owner")) == user["id"]]
    active = [p for p in mine if mc.is_active(p.meta)]
    far = mc.to_date("9999-12-31")
    due = sorted([p for p in active if (mc.to_date(p.meta.get("next_action_due")) or far) <= on],
                 key=lambda p: (mc.tier_rank(p.meta), mc.to_date(p.meta.get("next_action_due")), p.id))
    hot = [p for p in active if mc.is_hot(p.meta, on)]
    risky = [p for p in active if mc.risk_flags(p.meta)]
    vam = [p for p in active if mc.has_vam_predraft(p.body)]

    def due_label(p):
        d = mc.to_date(p.meta.get("next_action_due"))
        when = "today" if d == on else f"overdue {d.isoformat()}"
        nba = mc.norm(p.meta.get("nba")) or mc.norm(p.meta.get("next_action"))
        return f"{p.id} ({mc.norm(p.meta.get('tier')) or '-'}, {when})" + (f" — {nba}" if nba else "")

    lines = [f"Your book: {len(active)} active / {user.get('max_active', '-')} capacity"]
    lines.append(f"  Due or overdue ({len(due)}): " + (_fmt([due_label(p) for p in due]) or "nothing"))
    lines.append(f"  Hot ({len(hot)}): " + (_fmt([p.id for p in hot]) or "none"))
    lines.append(f"  At risk ({len(risky)}): "
                 + (_fmt([f"{p.id} ({', '.join(mc.risk_flags(p.meta))})" for p in risky]) or "none"))
    lines.append(f"  VAM pre-drafts waiting ({len(vam)}): " + (_fmt([p.id for p in vam]) or "none"))
    quota = user.get("daily_quota")
    try:
        quota_n = int(quota)
    except (TypeError, ValueError):
        quota_n = None
    keys = {mc.norm(user.get("id")).lower(), mc.norm(user.get("email")).lower()} - {""}
    used = sum(1 for t in mc.load_touches(root)
               if mc.norm(t.get("rep")).lower() in keys and mc.to_date(t.get("ts")) == on
               and mc.norm(t.get("status")) in ("drafted", "sent"))
    if quota_n is not None:
        lines.append(f"  Quota left today: {max(quota_n - used, 0)} / {quota_n}")
    else:
        lines.append(f"  Drafts today: {used} (no daily_quota set)")
    try:  # sending channels (ADR-0007); never let this break the banner
        import connect
        lines.append("  " + connect.status_line(root))
    except Exception:  # noqa: BLE001
        pass
    return lines


def _last_approval(root: Path, mc):
    """Date of the latest allocation approval in wiki/log.md (op 'assign', or
    op 'allocate' with 'approv' in the line), or None."""
    path = root / "wiki" / "log.md"
    if not path.is_file():
        return None
    latest = None
    pat = re.compile(r"^- \[(\d{4}-\d{2}-\d{2})[^\]]*\]\s*(\w+)\s*\|(.*)$")
    for line in mc.read_text(path).splitlines():
        m = pat.match(line.strip())
        if not m:
            continue
        op, rest = m.group(2), m.group(3).lower()
        if op == "assign" or (op == "allocate" and "approv" in rest):
            d = mc.to_date(m.group(1))
            if d and (latest is None or d > latest):
                latest = d
    return latest


def _manager_queue(root: Path, mc) -> list[str]:
    import datetime as dt

    lines = []
    marker = _last_approval(root, mc)
    pending = []
    alloc = root / "log" / "allocation"
    for p in sorted(alloc.glob("*.md")) if alloc.is_dir() else []:
        page = mc.read_page(p, root)
        status = mc.norm((page.meta or {}).get("status")).lower() if page else ""
        if status in ("approved", "applied", "rejected", "superseded"):
            continue
        d = mc.to_date(p.name)
        if d is None:
            try:
                d = dt.date.fromtimestamp(p.stat().st_mtime)
            except OSError:
                d = None
        if marker is None or (d is not None and d > marker):
            pending.append(p)
    latest_alloc = f" (latest log/allocation/{pending[-1].name})" if pending else ""
    lines.append(f"  Allocation proposals pending: {len(pending)}{latest_alloc}")
    review = [r for r in mc.read_csv(root / "log" / "review.csv") if not mc.norm(r.get("decision"))]
    lines.append(f"  Review queue: {len(review)} undecided (log/review.csv)")
    briefs = root / "log" / "briefs"
    files = sorted(briefs.glob("*.md")) if briefs.is_dir() else []
    if files:
        latest = files[-1]
        stale = "" if mc.to_date(latest.name) == mc.today() else "  <- not from today"
        lines.append(f"  Latest brief: log/briefs/{latest.name}{stale}")
    else:
        lines.append("  Latest brief: none yet")
    accounts = list(mc.iter_pages("account", root))
    pool = [p for p in accounts if not mc.norm(p.meta.get("owner")) and mc.is_active(p.meta)]
    owned = [p for p in accounts if mc.norm(p.meta.get("owner")) and mc.is_active(p.meta)]
    reps = [r for r in mc.load_reps(root) if r.get("role") != "inactive"]
    lines.append(f"  Team: {len(owned)} active owned accounts · {len(reps)} people · pool {len(pool)}")
    return lines


def run(no_pull: bool = False) -> None:
    import mama_common as mc

    mc.setup_stdout()
    root = mc.repo_root()
    notes: list[str] = []
    if not no_pull:
        w = _pull(root, mc)
        if w:
            notes.append(w)
    if mc.yaml is None:
        print("Sales Mama: " + mc.YAML_MISSING)
        return
    notes += _rebuild(root)
    on = mc.today()
    reps = mc.load_reps(root)
    user = mc.current_user(root)
    print("=" * 60)
    if user is None:
        email = mc.git_email(root) or "no git email set"
        print(f"Sales Mama ready · unknown user ({email}) · {on.strftime('%a %Y-%m-%d')}")
        if not reps:
            print("No rep profiles yet (bootstrap mode).")
        print("Run mama-setup to create your profile in reps/ (\"set me up for Sales Mama\").")
    else:
        role = user.get("role") or "rep"
        print(f"Sales Mama ready · {user.get('name') or user['id']} ({user['id']}, {role}) · "
              f"{on.strftime('%a %Y-%m-%d')}")
        if role == "manager":
            print("Manager queue:")
            for line in _manager_queue(root, mc):
                print(line)
            owns = any(mc.norm(p.meta.get("owner")) == user["id"] for p in mc.iter_pages("account", root))
            if owns:
                for line in _rep_queue(user, root, mc):
                    print(line)
            print("Try: /mama-manager · /mama-allocate · /mama-weekly")
        elif role == "inactive":
            print("Your profile is marked inactive. Ask the manager if that is a mistake.")
        else:
            for line in _rep_queue(user, root, mc):
                print(line)
            print("Try: /mama-day · /mama-book · /mama-replies")
    for n in notes:
        print(f"Warning: {n}")
    print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    try:
        ap = argparse.ArgumentParser(
            description="Sales Mama session start: pull, rebuild index and books, print the "
                        "current user's queue. Always exits 0.")
        ap.add_argument("--no-pull", action="store_true", help="skip git pull")
        args = ap.parse_args(argv)
    except SystemExit:  # --help or bad args: still never block the session
        return 0
    try:
        run(no_pull=args.no_pull)
    except Exception as exc:  # noqa: BLE001
        print(f"Sales Mama session start warning: {type(exc).__name__}: {exc}".splitlines()[0])
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except BaseException:  # noqa: BLE001 - never block a session
        code = 0
    sys.exit(0)
