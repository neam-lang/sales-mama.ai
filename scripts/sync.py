"""Save and share work: commit wiki/ raw/ log/ reps/ changes, then pull and push.

Claude Code runs this as the Stop hook (`--quiet`); run it by hand any time.

1. Stage only wiki/, raw/, log/ and reps/ (never wiki/index.md or
   wiki/books/, which are generated and gitignored). Nothing else is staged,
   so changes to knowledge/ or scripts/ stay for a reviewed commit/PR.
2. Commit as `mama(<user id or 'unknown'>): <summary of changed paths>`.
3. If a remote exists: `git pull --rebase --autostash`, `git push`; on a
   rejected push, pull and push once more.
4. On a rebase conflict: `git rebase --abort`, keep the local commit, and
   print plain-English next steps. Never force-push.
5. No remote: commit only and say so.

ALWAYS exits 0 (a Stop hook that exits 2 would stop Claude from finishing).

    python3 scripts/sync.py
    python3 scripts/sync.py --quiet      # print only problems and the result line
    python3 scripts/sync.py -m "note"    # append a note to the commit summary
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

SYNC_DIRS = ("wiki", "raw", "log", "reps", "company-check")
GENERATED = ("wiki/index.md", "wiki/books")


def excludes(root: Path, mc) -> list[str]:
    """Exclude pathspecs for generated files that .gitignore does not already
    cover (git add fails if an explicit pathspec names an ignored file)."""
    out = []
    for p in GENERATED:
        probe = p if p.endswith(".md") else f"{p}/x.md"
        code, _, _ = mc.run_git(["check-ignore", "-q", "--no-index", probe], cwd=root, timeout=15)
        if code != 0:
            out.append(f":(exclude){p}")
    return out


class Out:
    def __init__(self, quiet: bool):
        self.quiet = quiet

    def info(self, msg: str) -> None:
        if not self.quiet:
            print(msg)

    def warn(self, msg: str) -> None:
        print(msg)


def summarize(paths: list[str]) -> str:
    """'wiki/accounts (3), log (1), raw/signals (2)' style summary."""
    groups: Counter = Counter()
    for p in paths:
        parts = p.split("/")
        key = "/".join(parts[:2]) if len(parts) > 2 else parts[0] if len(parts) > 1 else p
        if parts[0] == "reps" or p in ("wiki/log.md", "wiki/suppression.csv"):
            key = p if parts[0] != "reps" else "reps"
        groups[key] += 1
    items = sorted(groups.items(), key=lambda kv: (-kv[1], kv[0]))
    text = ", ".join(f"{k} ({n})" if n > 1 else k for k, n in items[:6])
    if len(items) > 6:
        text += f", +{len(items) - 6} more"
    return text or "no changes"


def conflict_help(out: Out, files: list[str]) -> None:
    out.warn("Sync conflict: your changes and a teammate's changes touch the same lines.")
    out.warn("What happened: your work is SAFE in a local commit; the rebase was undone, nothing was pushed.")
    if files:
        out.warn("Conflicting file(s): " + ", ".join(files[:10]))
    out.warn("Next steps:")
    out.warn("  1. Ask the agent: \"resolve the sync conflict\" (it will rebase, fix only files you own, and push).")
    out.warn("  2. Or by hand: `git pull --rebase`, edit the conflicted files, `git add` them, "
             "`git rebase --continue`, then `python3 scripts/sync.py`.")
    out.warn("  3. If the files are someone else's (e.g. another rep's account), tell the manager.")
    out.warn("Never force-push.")


def pull_rebase(root: Path, mc, out: Out) -> str:
    """Return 'ok', 'conflict' or 'failed'."""
    code, so, se = mc.run_git(["pull", "--rebase", "--autostash"], cwd=root, timeout=120)
    if code == 0:
        return "ok"
    if mc.rebase_in_progress(root):
        _, conf, _ = mc.run_git(["diff", "--name-only", "--diff-filter=U"], cwd=root, timeout=30)
        mc.run_git(["rebase", "--abort"], cwd=root, timeout=60)
        conflict_help(out, [c for c in conf.splitlines() if c.strip()])
        return "conflict"
    msg = (se or so).strip().splitlines()
    out.warn(f"Sync warning: git pull failed ({msg[-1] if msg else f'exit {code}'}). "
             "Your work is committed locally; run `python3 scripts/sync.py` again when online.")
    return "failed"


def run(quiet: bool, note: str | None) -> None:
    import mama_common as mc

    mc.setup_stdout()
    out = Out(quiet)
    root = mc.repo_root()
    code, _, err = mc.run_git(["rev-parse", "--is-inside-work-tree"], cwd=root, timeout=15)
    if code != 0:
        out.warn("Sync skipped: this folder is not a git repository yet (mama-setup clones it).")
        return
    if mc.rebase_in_progress(root) or mc.merge_in_progress(root):
        out.warn("Sync skipped: a git rebase or merge is already in progress. Ask the agent to "
                 "\"finish the sync\" or run `git status` to see what's left. Never force-push.")
        return

    user = mc.current_user(root) if mc.yaml is not None else None
    uid = user["id"] if user else "unknown"

    present = [d for d in SYNC_DIRS if (root / d).exists()]
    committed = False
    if present:
        skip = excludes(root, mc)
        code, _, err = mc.run_git(["add", "-A", "--", *present, *skip], cwd=root, timeout=60)
        if code != 0:
            out.warn(f"Sync warning: git add failed: {err.strip().splitlines()[-1] if err.strip() else code}")
        code, staged, _ = mc.run_git(
            ["diff", "--cached", "--name-only", "--", *present], cwd=root, timeout=30)
        paths = [p for p in staged.splitlines() if p.strip()]
        if paths:
            summary = summarize(paths)
            if note:
                summary = f"{summary} — {note}"
            msg = f"mama({uid}): {summary}"
            # Pathspec keeps anything else the user staged by hand out of this commit.
            # Only folders with staged changes: git rejects pathspecs that match nothing.
            tops = sorted({p.split("/")[0] for p in paths})
            code, so, se = mc.run_git(["commit", "-m", msg, "--", *tops, *skip],
                                      cwd=root, timeout=60)
            if code == 0:
                committed = True
                out.info(f"Committed: {msg}")
            else:
                last = (se or so).strip().splitlines()
                out.warn(f"Sync warning: commit failed ({last[-1] if last else code}). "
                         "Check `git config user.name` and `user.email`.")
                return
    if not committed:
        out.info("Nothing new to commit in wiki/ raw/ log/ reps/.")

    remotes = mc.git_remotes(root)
    if not remotes:
        if committed:
            out.warn("Saved locally (no git remote configured, so nothing was pushed). "
                     "Add one with `git remote add origin <url>`.")
        return

    upstream = mc.git_upstream(root)
    _, branch, _ = mc.run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root, timeout=15)
    branch = branch.strip()
    if not upstream:
        if branch in ("", "HEAD"):
            out.warn("Sync skipped push: not on a branch (detached HEAD). Your work is committed locally.")
            return
        remote = "origin" if "origin" in remotes else remotes[0]
        code, heads, _ = mc.run_git(["ls-remote", "--heads", remote, branch], cwd=root, timeout=60)
        if code == 0 and heads.strip():
            # The branch exists on the remote: track it, then pull/push as usual.
            mc.run_git(["fetch", remote, branch], cwd=root, timeout=120)
            mc.run_git(["branch", f"--set-upstream-to={remote}/{branch}"], cwd=root, timeout=15)
        else:
            code, so, se = mc.run_git(["push", "-u", remote, branch], cwd=root, timeout=120)
            if code == 0:
                out.info(f"Pushed {branch} to {remote} (upstream set).")
            else:
                last = (se or so).strip().splitlines()
                out.warn(f"Sync warning: first push failed ({last[-1] if last else code}). "
                         "Your work is committed locally.")
            return

    code, ahead, _ = mc.run_git(["rev-list", "--count", "@{u}..HEAD"], cwd=root, timeout=15)
    for attempt in (1, 2):
        state = pull_rebase(root, mc, out)
        if state != "ok":
            return
        code, ahead, _ = mc.run_git(["rev-list", "--count", "@{u}..HEAD"], cwd=root, timeout=15)
        if code == 0 and ahead.strip() == "0":
            out.info("Up to date with the team.")
            return
        code, so, se = mc.run_git(["push"], cwd=root, timeout=120)
        if code == 0:
            out.info("Pushed to the team repo.")
            return
        if attempt == 1:
            out.info("Push was rejected (someone pushed first); pulling and retrying once...")
    last = (se or so).strip().splitlines()
    out.warn(f"Sync warning: push failed twice ({last[-1] if last else 'unknown error'}). "
             "Your work is committed locally; run `python3 scripts/sync.py` again later. "
             "Never force-push.")


def main(argv: list[str] | None = None) -> int:
    try:
        ap = argparse.ArgumentParser(
            description="Commit wiki/ raw/ log/ reps/ changes, pull --rebase, push (retry once). "
                        "Never force-pushes. Always exits 0.")
        ap.add_argument("--quiet", action="store_true", help="print only problems and results")
        ap.add_argument("-m", "--message", help="extra note for the commit summary")
        args = ap.parse_args(argv)
    except SystemExit:
        return 0
    try:
        run(args.quiet, args.message)
    except Exception as exc:  # noqa: BLE001
        print(f"Sales Mama sync warning: {type(exc).__name__}: {exc}".splitlines()[0])
    return 0


if __name__ == "__main__":
    try:
        main()
    except BaseException:  # noqa: BLE001 - never block Claude from stopping
        pass
    sys.exit(0)
