"""Find wiki pages by frontmatter. Default type: account.

Examples:
    python3 scripts/find.py --owner me --stage new
    python3 scripts/find.py --owner none --tier A --market SG
    python3 scripts/find.py --signal contract_win --due-before 2026-11-10
    python3 scripts/find.py --hot --json
    python3 scripts/find.py --type contact --text "finance"

Filters (all must match):
  --owner me|<id>|none   me = the current git user's rep id; none = unowned
  --stage/--tier/--market/--industry   exact match (case-insensitive);
                         comma-separated values mean "any of"
  --signal/--pain/--risk list membership in signals / pains / risk
  --due-before DATE      next_action_due on or before DATE (YYYY-MM-DD)
  --hot                  'hot' in risk, or tier A with score_updated today
  --text STR             case-insensitive substring of the whole file
Output: a compact table (default) or JSON (--json), sorted by tier, then
next_action_due, then id.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mama_common import (  # noqa: E402
    as_list, current_user, is_hot, iter_pages, norm, read_page, repo_root, setup_stdout, tier_rank,
    to_date, today,
)

FAR = dt.date(9999, 12, 31)
COLUMNS = {
    "account": ("id", "name", "market", "owner", "tier", "score", "stage", "next_action_due"),
    "contact": ("id", "name", "account", "title", "persona", "status"),
    "event": ("id", "name", "market", "dates", "venue"),
    "objection": ("id", "title", "category", "status", "times_seen"),
    "pattern": ("id", "step", "markets", "lang", "status", "sent", "replies"),
    "rep": ("id", "name", "role", "markets", "max_active"),
}


def _any_of(value, wanted: str) -> bool:
    opts = {w.strip().lower() for w in wanted.split(",") if w.strip()}
    return norm(value).lower() in opts


def _member(values, wanted: str) -> bool:
    opts = {w.strip().lower() for w in wanted.split(",") if w.strip()}
    return any(str(v).strip().lower() in opts for v in as_list(values))


def _jsonable(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def _cell(v) -> str:
    if v is None or v == "" or v == []:
        return "-"
    if isinstance(v, (list, tuple)):
        return ",".join(str(x) for x in v)
    return str(v)


def search(args, root: Path) -> list:
    owner_id = None
    if args.owner:
        o = args.owner.strip()
        if o.lower() == "me":
            user = current_user(root)
            if not user:
                raise SystemExit("find.py: --owner me needs a reps/ profile for your git email "
                                 "(run mama-setup).")
            owner_id = user["id"]
        elif o.lower() in ("none", "pool", "-"):
            owner_id = ""
        else:
            owner_id = o
    due_before = None
    if args.due_before:
        due_before = to_date(args.due_before)
        if due_before is None:
            raise SystemExit("find.py: --due-before needs YYYY-MM-DD")
    needle = args.text.lower() if args.text else None
    on = today()

    if args.type == "rep":
        pages = []
        for p in sorted((root / "reps").glob("*.md")) if (root / "reps").is_dir() else []:
            pg = read_page(p, root)
            if pg and pg.meta is not None:
                pages.append(pg)
    else:
        pages = list(iter_pages(None if args.type == "any" else args.type, root))
    hits = []
    for p in pages:
        m = p.meta or {}
        if owner_id is not None and norm(m.get("owner")) != owner_id:
            continue
        if args.stage and not _any_of(m.get("stage"), args.stage):
            continue
        if args.tier and not _any_of(m.get("tier"), args.tier):
            continue
        if args.market and not _any_of(m.get("market"), args.market):
            continue
        if args.industry and not _any_of(m.get("industry"), args.industry):
            continue
        if args.signal and not _member(m.get("signals"), args.signal):
            continue
        if args.pain and not _member(m.get("pains"), args.pain):
            continue
        if args.risk and not _member(m.get("risk"), args.risk):
            continue
        if due_before is not None:
            d = to_date(m.get("next_action_due"))
            if d is None or d > due_before:
                continue
        if args.hot and not is_hot(m, on):
            continue
        if needle and needle not in p.text.lower():
            continue
        hits.append(p)
    hits.sort(key=lambda p: (tier_rank(p.meta or {}),
                             to_date((p.meta or {}).get("next_action_due")) or FAR, p.id))
    return hits[: args.limit] if args.limit else hits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Filter wiki pages by frontmatter (default: accounts).",
        epilog="Example: find.py --owner me --tier A,B --due-before 2026-11-10")
    ap.add_argument("--type", default="account",
                    help="page type: account (default), contact, event, objection, pattern, faq, "
                         "rep, or any")
    ap.add_argument("--owner", help="me | <rep id> | none")
    ap.add_argument("--stage")
    ap.add_argument("--tier")
    ap.add_argument("--market", help="SG | MY | IN")
    ap.add_argument("--industry")
    ap.add_argument("--signal", help="signal term in `signals`")
    ap.add_argument("--pain", help="pain term in `pains`")
    ap.add_argument("--risk", help="flag in `risk`")
    ap.add_argument("--due-before", metavar="YYYY-MM-DD", help="next_action_due on or before")
    ap.add_argument("--hot", action="store_true", help="hot accounts only")
    ap.add_argument("--text", help="case-insensitive substring of the file text")
    ap.add_argument("--limit", type=int, default=0, help="max rows (0 = all)")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args(argv)
    setup_stdout()
    root = repo_root()
    hits = search(args, root)

    if args.json:
        rows = []
        for p in hits:
            d = {"path": p.rel, **_jsonable(p.meta or {})}
            d.setdefault("id", p.id)
            rows.append(d)
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    cols = COLUMNS.get(args.type, ("id", "type", "name", "status"))
    table = [list(cols)]
    for p in hits:
        m = dict(p.meta or {})
        m.setdefault("id", p.id)
        m["id"] = m.get("id") or p.id
        table.append([_cell(m.get(c))[:40] for c in cols])
    widths = [max(len(r[i]) for r in table) for i in range(len(cols))]
    for i, r in enumerate(table):
        print("  ".join(c.ljust(widths[j]) for j, c in enumerate(r)).rstrip())
        if i == 0:
            print("  ".join("-" * w for w in widths))
    print(f"({len(hits)} match{'es' if len(hits) != 1 else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
