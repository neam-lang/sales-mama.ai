"""Mirror the canonical skills .agents/skills/ into .claude/skills/.

Codex reads .agents/skills/; Claude Code reads .claude/skills/. Skills are
edited only in .agents/skills/ and copied here as real files (no symlinks, so
it works the same on Windows). Files in the mirror that no longer exist in the
source are deleted, along with empty folders.

    python3 scripts/sync_skills.py           # copy and prune
    python3 scripts/sync_skills.py --check   # exit 1 and list drift, change nothing

lint.py calls check() for its "skills mirror" check.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mama_common import repo_root, setup_stdout  # noqa: E402

SRC = Path(".agents") / "skills"
DST = Path(".claude") / "skills"
IGNORE_NAMES = {".DS_Store", "Thumbs.db", ".gitkeep"}
IGNORE_DIRS = {"__pycache__"}


def _files(base: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    if not base.is_dir():
        return out
    for p in base.rglob("*"):
        if p.name in IGNORE_NAMES or any(part in IGNORE_DIRS for part in p.parts):
            continue
        if p.is_file() or p.is_symlink():
            out[p.relative_to(base).as_posix()] = p
    return out


def diff(root: Path) -> list[tuple[str, str]]:
    """List of (kind, path) where kind is missing | changed | stale | symlink."""
    src, dst = _files(root / SRC), _files(root / DST)
    out: list[tuple[str, str]] = []
    for rel, p in sorted(src.items()):
        q = dst.get(rel)
        if q is None:
            out.append(("missing", rel))
        elif q.is_symlink():
            out.append(("symlink", rel))
        elif p.read_bytes() != q.read_bytes():
            out.append(("changed", rel))
    for rel in sorted(set(dst) - set(src)):
        out.append(("stale", rel))
    return out


def check(root: Path | None = None) -> list[str]:
    """Human-readable drift lines (empty list = in sync)."""
    root = root or repo_root()
    words = {"missing": "missing in .claude/skills", "changed": "differs from .agents/skills",
             "stale": "only in .claude/skills (stale)", "symlink": "is a symlink (must be a copy)"}
    return [f"{rel}: {words[kind]}" for kind, rel in diff(root)]


def sync(root: Path | None = None) -> list[str]:
    """Copy and prune; return a list of actions taken."""
    root = root or repo_root()
    src_base, dst_base = root / SRC, root / DST
    actions: list[str] = []
    for kind, rel in diff(root):
        target = dst_base / rel
        if kind == "stale":
            target.unlink()
            actions.append(f"deleted {DST.as_posix()}/{rel}")
            continue
        if target.is_symlink() or (target.exists() and not target.is_file()):
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_base / rel, target)  # follows a symlinked source, writes a real file
        actions.append(f"{'copied' if kind == 'missing' else 'updated'} {DST.as_posix()}/{rel}")
    # remove empty folders left behind in the mirror
    if dst_base.is_dir():
        for d in sorted((p for p in dst_base.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
            if d.name in IGNORE_DIRS:
                continue
            try:
                if not any(d.iterdir()) and not (src_base / d.relative_to(dst_base)).is_dir():
                    d.rmdir()
            except OSError:
                pass
    return actions


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Mirror .agents/skills/ (canonical) into .claude/skills/ as real files.")
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit 1 if the mirror is out of date; change nothing")
    args = ap.parse_args(argv)
    setup_stdout()
    root = repo_root()
    if args.check:
        drift = check(root)
        if drift:
            print(f"Skills mirror is out of date ({len(drift)} difference(s)):")
            for line in drift:
                print(f"  - {line}")
            print("Fix: python3 scripts/sync_skills.py")
            return 1
        n = len(_files(root / SRC))
        print(f"Skills mirror OK ({n} file(s)).")
        return 0
    actions = sync(root)
    for a in actions:
        print(a)
    print(f"Skills mirror synced ({len(actions)} change(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
