"""Shared helpers for the Sales Mama scripts.

Import from any script in scripts/:

    from mama_common import repo_root, current_user, iter_pages, ...

What is here:
- repo_root()            walk up to the folder that contains AGENTS.md
- read_page / write_page frontmatter (YAML between leading '---' lines) that
                         keeps the markdown body byte-for-byte
- update_frontmatter     change a few top-level keys in place, keeping comments
- current_user()         `git config user.email` (or env MAMA_USER_EMAIL)
                         matched against reps/*.md -> dict with id and role
- slugify / legal_slug   lowercase-kebab ids
- run_git(args)          returns (code, stdout, stderr) and never raises
- load_yaml / read_csv / append_csv
- iter_pages(type=None)  every wiki/**.md page that has frontmatter
- today()                date.today(), or env MAMA_TODAY=YYYY-MM-DD (tests)

Python 3.10+, PyYAML is the only third-party dependency. Works on macOS,
Linux and Windows. Run `python3 scripts/mama_common.py --help` for a quick
self-description, or `--whoami` to see how the current user resolves.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

try:  # PyYAML is required, but let callers decide how loudly to fail.
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - exercised only without PyYAML
    yaml = None  # type: ignore

# ----------------------------------------------------------------------------
# Constants shared by several scripts
# ----------------------------------------------------------------------------
MARKETS = ("SG", "MY", "IN")
STAGES = (
    "new", "researched", "contacted", "replied", "meeting", "handed_over",
    "nurture", "closed_lost", "do_not_contact",
)
# Accounts in these stages do not count against a rep's capacity.
CLOSED_STAGES = frozenset({"handed_over", "nurture", "closed_lost", "do_not_contact"})
TIERS = ("A", "B", "C")
GENERATED = ("wiki/index.md", "wiki/books/")  # gitignored, rebuilt each session
YAML_MISSING = "PyYAML is missing: run `python3 -m pip install --user pyyaml`"


def require_yaml() -> None:
    """Raise RuntimeError with an install hint if PyYAML is not importable."""
    if yaml is None:
        raise RuntimeError(YAML_MISSING)


def setup_stdout() -> None:
    """Never crash on a console that cannot print some character (Windows)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


# ----------------------------------------------------------------------------
# Repo root and dates
# ----------------------------------------------------------------------------
def _walk_up(start: Path) -> Path | None:
    try:
        p = start.resolve()
    except OSError:
        return None
    if p.is_file():
        p = p.parent
    for cand in (p, *p.parents):
        if (cand / "AGENTS.md").is_file():
            return cand
    return None


def repo_root(start: str | os.PathLike | None = None) -> Path:
    """Folder containing AGENTS.md.

    Order: explicit `start`, env MAMA_ROOT, this script's folder, the current
    directory. Script location wins over cwd so a run from inside another
    project that also has an AGENTS.md still finds the right repo.
    """
    cands: list[Path] = []
    if start is not None:
        cands.append(Path(start))
    elif os.environ.get("MAMA_ROOT"):
        cands.append(Path(os.environ["MAMA_ROOT"]))
    cands += [Path(__file__).resolve().parent, Path.cwd()]
    for c in cands:
        found = _walk_up(c)
        if found:
            return found
    return Path.cwd().resolve()


def today() -> dt.date:
    """Today's date; env MAMA_TODAY=YYYY-MM-DD overrides (used by selftest)."""
    env = os.environ.get("MAMA_TODAY", "").strip()
    if env:
        d = to_date(env)
        if d:
            return d
    return dt.date.today()


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def to_date(value: Any) -> dt.date | None:
    """Best-effort date from a YAML date, datetime or 'YYYY-MM-DD...' string."""
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    m = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", str(value))
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def norm(value: Any) -> str:
    """Trimmed string; None -> ''."""
    return "" if value is None else str(value).strip()


def as_list(value: Any) -> list:
    """None -> [], scalar -> [scalar], list/tuple/set -> list, dict -> keys."""
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, set)):
        return [v for v in value if v is not None and v != ""]
    if isinstance(value, dict):
        return list(value.keys())
    return [value]


def rel_posix(path: Path, root: Path | None = None) -> str:
    root = root or repo_root()
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# ----------------------------------------------------------------------------
# Text files, YAML and CSV
# ----------------------------------------------------------------------------
def read_text(path: Path) -> str:
    """Read UTF-8 text exactly (no newline translation)."""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def write_text(path: Path, text: str) -> None:
    """Write UTF-8 text exactly (no newline translation), creating folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def load_yaml(path: Path, default: Any = None, errors: list[str] | None = None) -> Any:
    """Parse a YAML file. Missing, empty or comment-only -> `default`.

    Parse errors are appended to `errors` (if given) and return `default`.
    """
    try:
        if not path.is_file():
            return default
        require_yaml()
        data = yaml.safe_load(read_text(path))
        return default if data is None else data
    except Exception as exc:  # noqa: BLE001
        if errors is not None:
            errors.append(f"{path.name}: {exc}".splitlines()[0])
        return default


def read_csv(path: Path) -> list[dict[str, str]]:
    """Rows of a CSV with a header line. Missing file -> []."""
    if not path.is_file():
        return []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            return [
                {(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None}
                for row in csv.DictReader(fh)
            ]
    except Exception:  # noqa: BLE001
        return []


def append_csv(path: Path, row: dict[str, Any], fieldnames: Iterable[str]) -> None:
    """Append one row; writes the header first if the file is new or empty."""
    fieldnames = list(fieldnames)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.is_file() or path.stat().st_size == 0
    with open(path, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fieldnames})


def append_log(op: str, user: str, target: str, summary: str, root: Path | None = None) -> None:
    """Append one line to wiki/log.md in the AGENTS.md log format."""
    root = root or repo_root()
    path = root / "wiki" / "log.md"
    line = f"- [{now_stamp()}] {op} | {user or 'unknown'} | {target} | {summary}\n"
    existing = read_text(path) if path.is_file() else "# Sales Mama log\n"
    if existing and not existing.endswith("\n"):
        existing += "\n"
    write_text(path, existing + line)


# ----------------------------------------------------------------------------
# Frontmatter
# ----------------------------------------------------------------------------
def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (yaml_text, body). yaml_text is None when there is no frontmatter.

    Frontmatter is YAML between a first line '---' and the next line that is
    '---' (or '...'). The body is everything after that closing line, verbatim.
    """
    t = text[1:] if text.startswith("﻿") else text
    lines = t.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n").rstrip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n").rstrip() in ("---", "..."):
            return "".join(lines[1:i]), "".join(lines[i + 1:])
    return None, text


def parse_frontmatter(text: str) -> tuple[dict | None, str, str | None]:
    """Return (meta, body, error). meta is None if there is no frontmatter
    or it does not parse to a mapping; error explains a parse failure."""
    fm, body = split_frontmatter(text)
    if fm is None:
        return None, body, None
    require_yaml()
    try:
        data = yaml.safe_load(fm)
    except Exception as exc:  # noqa: BLE001
        return None, body, f"frontmatter is not valid YAML: {str(exc).splitlines()[0]}"
    if data is None:
        return {}, body, None
    if not isinstance(data, dict):
        return None, body, "frontmatter is not a YAML mapping"
    return data, body, None


class _Dumper(yaml.SafeDumper if yaml else object):  # type: ignore[misc]
    pass


class _Top(dict):
    """Marker: the top-level mapping is always written in block style."""


def _is_scalar(v: Any) -> bool:
    return v is None or isinstance(v, (bool, int, float, dt.date)) or (
        isinstance(v, str) and "\n" not in v)


if yaml is not None:
    def _repr_none(dumper, _value):
        return dumper.represent_scalar("tag:yaml.org,2002:null", "")

    def _repr_str(dumper, value):
        style = "|" if "\n" in value else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)

    def _repr_list(dumper, value):
        flow = all(_is_scalar(x) for x in value)
        return dumper.represent_sequence("tag:yaml.org,2002:seq", value, flow_style=flow)

    def _repr_dict(dumper, value):
        flow = all(_is_scalar(x) for x in value.values())
        return dumper.represent_mapping("tag:yaml.org,2002:map", value.items(), flow_style=flow)

    def _repr_top(dumper, value):
        return dumper.represent_mapping("tag:yaml.org,2002:map", value.items(), flow_style=False)

    _Dumper.add_representer(type(None), _repr_none)
    _Dumper.add_representer(str, _repr_str)
    _Dumper.add_representer(list, _repr_list)
    _Dumper.add_representer(tuple, _repr_list)
    _Dumper.add_representer(dict, _repr_dict)
    _Dumper.add_representer(_Top, _repr_top)


def dump_yaml(data: Any) -> str:
    """YAML in the style of the templates: keys in order, top level in block
    style, empty for null, flow style for lists/maps of scalars
    (`signals: [a, b]`, `score_parts: {fit: 0.8}`), literal blocks for
    multiline strings (`signature: |`)."""
    require_yaml()
    if isinstance(data, dict):
        data = _Top(data)
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=1000)


def compose_page(meta: dict, body: str) -> str:
    nl = "\r\n" if "\r\n" in body else "\n"
    fm = dump_yaml(meta)
    if nl != "\n":
        fm = fm.replace("\n", nl)
    return f"---{nl}{fm}---{nl}{body}"


@dataclass
class Page:
    path: Path
    rel: str                 # posix path relative to repo root
    meta: dict | None        # None if no (valid) frontmatter
    body: str
    text: str
    error: str | None = None

    @property
    def id(self) -> str:
        return norm((self.meta or {}).get("id")) or self.path.stem

    @property
    def type(self) -> str:
        return norm((self.meta or {}).get("type"))


def read_page(path: Path, root: Path | None = None) -> Page | None:
    """Read a markdown page; None if the file cannot be read."""
    try:
        text = read_text(path)
    except Exception:  # noqa: BLE001
        return None
    meta, body, err = parse_frontmatter(text)
    return Page(path=path, rel=rel_posix(path, root), meta=meta, body=body, text=text, error=err)


def write_page(path: Path, meta: dict, body: str) -> None:
    """Write frontmatter + body. The body is written exactly as given.
    (Comments in the old frontmatter are not kept; use update_frontmatter
    to change a few keys and keep them.)"""
    write_text(path, compose_page(meta, body))


_KEY_RE = re.compile(r"^([A-Za-z_][\w\-]*)[ \t]*:(.*)$")


def update_frontmatter(path: Path, changes: dict[str, Any]) -> None:
    """Set top-level keys in a page's frontmatter, editing only their lines.

    Other lines (including comments) and the body stay byte-for-byte. A
    trailing '# comment' on a replaced one-line key is kept. Keys not present
    are appended at the end of the frontmatter. If the in-place edit does not
    round-trip, falls back to write_page (comments lost, body kept).
    """
    text = read_text(path)
    fm, body = split_frontmatter(text)
    if fm is None:
        raise ValueError(f"{path} has no frontmatter")
    nl = "\r\n" if "\r\n" in fm else "\n"
    lines = fm.splitlines(keepends=True)
    todo = dict(changes)
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _KEY_RE.match(line.rstrip("\r\n"))
        if not m or m.group(1) not in todo:
            out.append(line)
            i += 1
            continue
        key = m.group(1)
        j = i + 1  # skip the old value's continuation lines
        while j < len(lines) and (
            lines[j][:1] in (" ", "\t") or lines[j].startswith("- ") or lines[j].strip() == "-"
        ):
            j += 1
        new = dump_yaml({key: todo.pop(key)})
        new_lines = new.splitlines()
        rest = m.group(2)
        cm = re.search(r"\s+(#.*)$", rest)
        if cm and len(new_lines) == 1 and "'" not in rest and '"' not in rest:
            new_lines[0] = f"{new_lines[0]}  {cm.group(1)}"
        out.extend(nl_line + nl for nl_line in new_lines)
        i = j
    if todo:
        if out and not out[-1].endswith(("\n", "\r")):
            out[-1] += nl
        out.extend(x + nl for x in dump_yaml(todo).splitlines())
    new_fm = "".join(out)
    new_text = f"---{nl}{new_fm}---{nl}{body}"
    meta_new, body_new, err = parse_frontmatter(new_text)
    old_meta, _, _ = parse_frontmatter(text)
    expected = dict(old_meta or {})
    expected.update(changes)
    if err or meta_new is None or body_new != body or any(
        meta_new.get(k) != v for k, v in expected.items()
    ):
        write_page(path, expected, body)
        return
    write_text(path, new_text)


def section(body: str, heading: str) -> str:
    """Text under '## <heading>' (up to the next '#'/'##' heading), with HTML
    comments removed. Matching ignores case and anything after the heading
    text, so 'Call brief' also finds '## Call brief (2026-11-03)'."""
    lines = body.splitlines()
    want = heading.strip().lower()
    buf: list[str] = []
    inside = False
    for line in lines:
        m = re.match(r"^(#{1,2})\s+(.*?)\s*$", line)
        if m:
            if inside:
                break
            if m.group(2).lower().startswith(want):
                inside = True
            continue
        if inside:
            buf.append(line)
    return strip_comments("\n".join(buf)).strip()


def strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


# ----------------------------------------------------------------------------
# Wiki pages
# ----------------------------------------------------------------------------
def iter_pages(type: str | None = None, root: Path | None = None) -> Iterator[Page]:  # noqa: A002
    """Every wiki/**.md page with frontmatter, sorted by path.

    Skips the generated wiki/index.md and wiki/books/. `type` filters on the
    frontmatter `type` field (e.g. 'account', 'contact', 'objection').
    Pages whose frontmatter fails to parse are yielded only when type is None
    (with page.meta None and page.error set) so lint can report them.
    """
    root = root or repo_root()
    wiki = root / "wiki"
    if not wiki.is_dir():
        return
    for path in sorted(wiki.rglob("*.md")):
        rel = rel_posix(path, root)
        if rel == "wiki/index.md" or rel.startswith("wiki/books/"):
            continue
        page = read_page(path, root)
        if page is None:
            continue
        if page.meta is None:
            if page.error and type is None:
                yield page
            continue
        if type is not None and page.type != type:
            continue
        yield page


def link_id(value: Any, folder: str = "accounts") -> str:
    """'[[accounts/x]]', 'accounts/x', 'wiki/accounts/x.md' or 'x' -> 'x'."""
    s = norm(value)
    s = re.sub(r"^\[\[|\]\]$", "", s).split("|")[0].split("#")[0].strip()
    s = re.sub(r"\.md$", "", s)
    for prefix in ("wiki/", f"{folder}/"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s


def is_active(meta: dict) -> bool:
    return norm(meta.get("stage")) not in CLOSED_STAGES


def risk_flags(meta: dict) -> list[str]:
    """Risk flags other than 'hot' (hot is a priority, not a risk)."""
    return [str(r) for r in as_list(meta.get("risk")) if not str(r).lower().startswith("hot")]


def is_hot(meta: dict, on: dt.date | None = None) -> bool:
    """Hot = a 'hot' flag in `risk`, or tier A with score_updated today."""
    on = on or today()
    if any(str(r).lower().startswith("hot") for r in as_list(meta.get("risk"))):
        return True
    return norm(meta.get("tier")).upper() == "A" and to_date(meta.get("score_updated")) == on


def tier_rank(meta: dict) -> int:
    t = norm(meta.get("tier")).upper()
    return TIERS.index(t) if t in TIERS else len(TIERS)


def stage_rank(stage: str) -> int:
    return STAGES.index(stage) if stage in STAGES else len(STAGES)


def has_vam_predraft(body: str) -> bool:
    return bool(section(body, "VAM notes"))


# ----------------------------------------------------------------------------
# Identity
# ----------------------------------------------------------------------------
def git_email(root: Path | None = None) -> str:
    env = os.environ.get("MAMA_USER_EMAIL", "").strip()
    if env:
        return env
    code, out, _ = run_git(["config", "user.email"], cwd=root, timeout=15)
    return out.strip() if code == 0 else ""


def load_reps(root: Path | None = None) -> list[dict]:
    """Frontmatter of every reps/*.md that has frontmatter, plus '_path'
    (repo-relative) and 'id' (defaults to the file name)."""
    root = root or repo_root()
    reps = []
    folder = root / "reps"
    if not folder.is_dir():
        return reps
    for p in sorted(folder.glob("*.md")):
        page = read_page(p, root)
        if page is None or page.meta is None:
            continue
        meta = dict(page.meta)
        meta["id"] = norm(meta.get("id")) or p.stem
        meta["role"] = norm(meta.get("role")) or "rep"
        meta["_path"] = page.rel
        reps.append(meta)
    return reps


def current_user(root: Path | None = None) -> dict | None:
    """The reps/*.md entry whose `email` matches the git email (case-
    insensitive), with at least 'id', 'role', 'email', '_path'; or None."""
    root = root or repo_root()
    email = git_email(root).lower()
    if not email:
        return None
    for rep in load_reps(root):
        if norm(rep.get("email")).lower() == email:
            return rep
    return None


# ----------------------------------------------------------------------------
# Slugs
# ----------------------------------------------------------------------------
_LEGAL_SUFFIXES = (
    "pte-ltd", "pte-limited", "private-limited", "pvt-ltd", "sdn-bhd", "berhad", "bhd",
    "llp", "limited", "ltd", "plc", "inc", "corporation", "corp", "opc",
)


def slugify(text: Any) -> str:
    """'Café & Co. (S) Pte Ltd' -> 'cafe-and-co-s-pte-ltd'."""
    t = unicodedata.normalize("NFKD", norm(text)).encode("ascii", "ignore").decode("ascii")
    t = t.lower().replace("&", " and ")
    t = re.sub(r"[^a-z0-9]+", "-", t)
    return re.sub(r"-{2,}", "-", t).strip("-")


def legal_slug(name: Any, market: str | None = None, taken: Iterable[str] = ()) -> str:
    """Account id per AGENTS.md: legal name without 'pte ltd', 'sdn bhd',
    'pvt ltd' and the like; '-sg/-my/-in' added if the slug is taken."""
    s = slugify(name)
    changed = True
    while changed:
        changed = False
        for suf in _LEGAL_SUFFIXES:
            if s.endswith("-" + suf):
                s = s[: -len(suf) - 1]
                changed = True
    taken = set(taken)
    if market and s in taken:
        s = f"{s}-{market.lower()}"
    return s


# ----------------------------------------------------------------------------
# git
# ----------------------------------------------------------------------------
def run_git(args: list[str], cwd: Path | None = None, timeout: int = 120,
            env: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Run `git <args>`; return (code, stdout, stderr). Never raises.
    127 = git missing, 124 = timeout. Terminal prompts are disabled."""
    e = dict(os.environ)
    e["GIT_TERMINAL_PROMPT"] = "0"
    if env:
        e.update(env)
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd or repo_root()), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, env=e,
            stdin=subprocess.DEVNULL,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", "git is not installed or not on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", f"git {' '.join(args)} timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return 1, "", f"{type(exc).__name__}: {exc}"


def git_dir(root: Path) -> Path | None:
    code, out, _ = run_git(["rev-parse", "--git-dir"], cwd=root, timeout=15)
    if code != 0 or not out.strip():
        return None
    p = Path(out.strip())
    return p if p.is_absolute() else (root / p)


def rebase_in_progress(root: Path) -> bool:
    g = git_dir(root)
    return bool(g) and ((g / "rebase-merge").exists() or (g / "rebase-apply").exists())


def merge_in_progress(root: Path) -> bool:
    g = git_dir(root)
    return bool(g) and (g / "MERGE_HEAD").exists()


def git_upstream(root: Path) -> str:
    code, out, _ = run_git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=root, timeout=15)
    return out.strip() if code == 0 else ""


def git_remotes(root: Path) -> list[str]:
    code, out, _ = run_git(["remote"], cwd=root, timeout=15)
    return [r.strip() for r in out.splitlines() if r.strip()] if code == 0 else []


# ----------------------------------------------------------------------------
# Logs
# ----------------------------------------------------------------------------
TOUCH_FIELDS = ("ts", "rep", "account", "contact", "channel", "step", "pattern",
                "products", "status", "reply_class", "ref")


def load_touches(root: Path | None = None) -> list[dict[str, str]]:
    return read_csv((root or repo_root()) / "log" / "touches.csv")


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Shared helpers for Sales Mama scripts (import, don't run). "
                    "Use --whoami to check identity resolution.")
    ap.add_argument("--whoami", action="store_true",
                    help="print the repo root, git email and matched rep profile")
    args = ap.parse_args(argv)
    setup_stdout()
    if args.whoami:
        root = repo_root()
        user = current_user(root)
        print(f"repo root : {root}")
        print(f"git email : {git_email(root) or '(not set)'}")
        if user:
            print(f"user      : {user['id']} ({user.get('role')}) from {user['_path']}")
        else:
            print("user      : unknown (run mama-setup)")
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(_main())
