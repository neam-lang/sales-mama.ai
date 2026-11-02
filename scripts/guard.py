"""Write guard for Sales Mama (Claude Code PreToolUse hook).

Claude Code runs this before Edit, Write, MultiEdit and NotebookEdit, passing
the hook JSON on stdin ({"tool_name": ..., "tool_input": {...}, "cwd": ...}).
Exit 2 with a one-line reason on stderr blocks the write; exit 0 allows it.

Blocked (exit 2):
- a non-manager writes knowledge/, AGENTS.md, CLAUDE.md, scripts/, runner/,
  .agents/, .claude/ or .codex/
- anyone edits an EXISTING file under raw/ (adding new raw files is fine)
- a non-manager edits an account page whose `owner` is set to someone else
- a non-manager edits another person's reps/ file, or writes `role: manager`
  into any reps/ file
- anyone (manager included, even during bootstrap) writes a secrets file into
  the repo (.env, gmail.json, whatsapp.json, OAuth client or *token*.json) or
  text containing an access token, refresh token, client secret or private key.
  Secrets live in ~/.config/sales-mama/ (ADR-0007).

Allowed:
- everything while reps/ has no rep files yet (bootstrap)
- a user without a rep file creating reps/<slug>.md whose content has
  `role: rep` (that is what mama-setup does)
- paths outside the repo, and every other write

Identity: `git config user.email` (or env MAMA_USER_EMAIL) matched against
reps/*.md `email`. Users with no rep file are treated like reps.

Malformed input or an internal error -> exit 0 with a warning on stderr
(fail open). The guard prevents mistakes; GitHub CODEOWNERS and branch
protection are the real control.

Test by hand:
    echo '{"tool_name":"Write","tool_input":{"file_path":"knowledge/x.md","content":"x"}}' \\
      | python3 scripts/guard.py; echo "exit $?"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path, PureWindowsPath

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

PROTECTED_DIRS = ("knowledge/", "scripts/", "runner/", ".agents/", ".claude/", ".codex/")
PROTECTED_FILES = ("AGENTS.md", "CLAUDE.md")
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
CASE_INSENSITIVE_FS = sys.platform.startswith(("win", "darwin"))
ROLE_MANAGER_RE = re.compile(r"""^\s*role\s*:\s*["']?manager\b""", re.M | re.I)
SECRET_NAME_RE = re.compile(r"(^|/)(\.env(\.[^/]*)?|gmail\.json|whatsapp\.json|google-oauth-client[^/]*\.json|"
                            r"client_secret[^/]*\.json|[^/]*token[^/]*\.json)$", re.I)
# Shared with lint.py: Google access token, Meta token, OAuth refresh token value, Google client secret, PEM key.
SECRET_RE = re.compile(r"ya29\.[\w-]{20,}|EAA[A-Za-z0-9]{40,}|\"refresh_token\"\s*:\s*\"[^\"]{10,}\"|"
                       r"GOCSPX-[\w-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----")


class Block(Exception):
    """Raised with the one-line reason when a write must be blocked."""


def _warn(msg: str) -> None:
    print(f"guard.py warning: {msg}", file=sys.stderr)


def resolve_rel(file_path: str, root: Path, cwd: str | None) -> str | None:
    """Repo-relative posix path for file_path, or None if outside the repo."""
    raw = file_path.strip()
    if not raw:
        return None
    win = PureWindowsPath(raw)
    if os.name != "nt" and win.drive and not raw.startswith("/"):
        # A Windows absolute path seen on a POSIX machine: compare as strings.
        root_s = str(root).replace("\\", "/").rstrip("/").lower()
        cand = raw.replace("\\", "/")
        return cand[len(root_s) + 1:] if cand.lower().startswith(root_s + "/") else None
    p = Path(raw.replace("\\", "/")) if os.name != "nt" else Path(raw)
    if not p.is_absolute():
        base = Path(cwd) if cwd else root
        p = base / p
    try:
        p = p.resolve(strict=False)
        r = root.resolve(strict=False)
    except OSError:
        return None
    try:
        return p.relative_to(r).as_posix()
    except ValueError:
        pass
    if CASE_INSENSITIVE_FS:
        ps, rs = p.as_posix(), r.as_posix().rstrip("/")
        if ps.lower().startswith(rs.lower() + "/"):
            return ps[len(rs) + 1:]
    return None


def _same(a: str, b: str) -> bool:
    return a.lower() == b.lower() if CASE_INSENSITIVE_FS else a == b


def _startswith(rel: str, prefix: str) -> bool:
    return rel.lower().startswith(prefix.lower()) if CASE_INSENSITIVE_FS else rel.startswith(prefix)


def new_texts(tool: str, ti: dict) -> list[str]:
    """The strings this tool call would write."""
    if tool == "Write":
        return [str(ti.get("content") or "")]
    if tool == "Edit":
        return [str(ti.get("new_string") or "")]
    if tool == "MultiEdit":
        return [str(e.get("new_string") or "") for e in (ti.get("edits") or []) if isinstance(e, dict)]
    if tool == "NotebookEdit":
        return [str(ti.get("new_source") or "")]
    return []


def resulting_text(tool: str, ti: dict, path: Path) -> str | None:
    """Best-effort file content after the call (Write/Edit/MultiEdit)."""
    if tool == "Write":
        return str(ti.get("content") or "")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    edits = [ti] if tool == "Edit" else [e for e in (ti.get("edits") or []) if isinstance(e, dict)]
    for e in edits:
        old, new = str(e.get("old_string") or ""), str(e.get("new_string") or "")
        if old and old in text:
            text = text.replace(old, new) if e.get("replace_all") else text.replace(old, new, 1)
    return text


def _role_in(text: str | None, mc) -> str | None:
    if text is None:
        return None
    try:
        meta, _, _ = mc.parse_frontmatter(text)
    except Exception:  # noqa: BLE001
        meta = None
    if isinstance(meta, dict) and meta.get("role") is not None:
        return mc.norm(meta.get("role")).lower()
    m = re.search(r"""^\s*role\s*:\s*["']?([A-Za-z_]+)""", text, re.M)
    return m.group(1).lower() if m else None


def rep_files(root: Path) -> list[Path]:
    folder = root / "reps"
    if not folder.is_dir():
        return []
    return [p for p in folder.glob("*.md") if p.name.lower() != "readme.md"]


def check(payload: dict, root: Path, mc) -> None:
    """Raise Block(reason) if the write must be blocked."""
    tool = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input")
    if tool not in WRITE_TOOLS or not isinstance(ti, dict):
        return
    file_path = ti.get("notebook_path") if tool == "NotebookEdit" else ti.get("file_path")
    if not file_path:
        file_path = ti.get("file_path") or ti.get("notebook_path")
    if not isinstance(file_path, str) or not file_path.strip():
        _warn("no file_path in tool_input; allowing")
        return
    rel = resolve_rel(file_path, root, payload.get("cwd"))
    if rel is None or rel in ("", "."):
        return  # outside the repo
    target = root / rel

    # Secrets never go in the repo, whoever writes them (ADR-0007).
    if SECRET_NAME_RE.search(rel):
        raise Block(f"{rel} looks like a secrets file; secrets live outside the repo in ~/.config/sales-mama/ "
                    "(use scripts/connect.py).")
    if any(SECRET_RE.search(t or "") for t in new_texts(tool, ti)):
        raise Block(f"the text for {rel} contains what looks like a token or private key; keep secrets in "
                    "~/.config/sales-mama/, never in the repo.")

    if not rep_files(root):
        return  # bootstrap: no rep profiles yet

    # raw/ is immutable for everyone, manager included.
    if _startswith(rel, "raw/") and target.is_file():
        raise Block(f"raw/ files are immutable: {rel} already exists. Add a new file instead "
                    "(retention deletions go through mama-weekly).")

    user = mc.current_user(root)
    role = mc.norm((user or {}).get("role")).lower() or None
    if role == "manager":
        return
    who = f"{user['id']} ({role or 'rep'})" if user else "an unknown user (no reps/ profile)"

    if rel in PROTECTED_FILES or any(_same(rel, f) for f in PROTECTED_FILES) or any(
            _startswith(rel, d) for d in PROTECTED_DIRS):
        raise Block(f"{rel} is manager-owned; {who} may not change it. Propose the change to "
                    "the manager instead.")

    if _startswith(rel, "reps/"):
        if user:
            if not _same(rel, user["_path"]):
                raise Block(f"{rel} is not your profile ({user['_path']}); only the manager "
                            "edits other people's reps/ files.")
        else:
            if target.exists():
                raise Block(f"{rel} belongs to someone else; run mama-setup to create your own "
                            "profile.")
            if "/" in rel[len("reps/"):] or not rel.lower().endswith(".md"):
                raise Block(f"new profiles must be reps/<id>.md, not {rel}.")
            if _role_in(resulting_text(tool, ti, target), mc) != "rep":
                raise Block(f"a new profile ({rel}) must contain `role: rep`; only the manager "
                            "sets other roles.")
        if any(ROLE_MANAGER_RE.search(t) for t in new_texts(tool, ti)) or \
                _role_in(resulting_text(tool, ti, target), mc) == "manager":
            raise Block("only the manager can set `role: manager` in reps/.")
        return

    # Account pages: only the owner (or the manager) may edit an owned page.
    if target.is_file() and _startswith(rel, "wiki/"):
        page = mc.read_page(target, root)
        meta = page.meta if page else None
        is_account = _startswith(rel, "wiki/accounts/") or (meta or {}).get("type") == "account"
        if is_account and isinstance(meta, dict):
            owner = mc.norm(meta.get("owner"))
            mine = mc.norm((user or {}).get("id"))
            if owner and owner != mine:
                raise Block(f"{rel} is owned by {owner}; {who} may only edit accounts they own. "
                            "Ask the manager to reassign it, or suggest the change to the owner.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Sales Mama PreToolUse write guard. Reads Claude Code hook JSON on stdin; "
                    "exit 2 + reason blocks the write, exit 0 allows it.")
    ap.parse_args(argv)
    try:
        import mama_common as mc
    except Exception as exc:  # noqa: BLE001
        _warn(f"cannot load mama_common ({exc}); allowing")
        return 0
    try:
        data = sys.stdin.read()
        payload = json.loads(data) if data.strip() else None
    except Exception as exc:  # noqa: BLE001
        _warn(f"malformed hook input ({type(exc).__name__}); allowing")
        return 0
    if not isinstance(payload, dict):
        _warn("hook input is not a JSON object; allowing")
        return 0
    try:
        check(payload, mc.repo_root(), mc)
    except Block as b:
        print(f"Sales Mama guard: {b}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        _warn(f"internal error ({type(exc).__name__}: {exc}); allowing")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
