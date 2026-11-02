"""Write the CRM update row and the meeting touch for mama-handover.

Re-reads wiki/accounts/<id>.md (set `stage`, `next_action`, `next_action_due`
first), checks the current user is its owner or the manager, then:
- appends one row to log/crm-updates/<today>.csv with exactly the
  knowledge/crm_mapping.yaml `import:` columns as header (default: Account
  Name, Stage, Next Step, Owner Email, Notes);
- appends a `meeting / meeting_held` row to log/touches.csv.
Products must exist in knowledge/products/ (rule 4).

    python3 scripts/crm_update.py --id harbourlight-foods --notes "2-site pilot, decision by 30 Nov" \\
        --contact tan-wei-harbourlight-foods --products it-care --ref raw/notes/2026-11-05-harbourlight-foods-call.md
    python3 scripts/crm_update.py --id harbourlight-foods --notes "..." --dry-run   # print, write nothing
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402

DEFAULT_COLUMNS = ["Account Name", "Stage", "Next Step", "Owner Email", "Notes"]


def columns(root: Path) -> list[str]:
    mapping = mc.load_yaml(root / "knowledge" / "crm_mapping.yaml", {}) or {}
    cols = [mc.norm(c) for c in mc.as_list(mapping.get("import")) if mc.norm(c)]
    return cols or DEFAULT_COLUMNS


def handover(root: Path, user: dict, acc: str, notes: str, contact: str = "", products: str = "",
             ref: str = "", dry_run: bool = False) -> dict:
    import lint

    path = root / "wiki" / "accounts" / f"{acc}.md"
    page = mc.read_page(path, root) if path.is_file() else None
    if not page or not page.meta:
        raise ValueError(f"no account page wiki/accounts/{acc}.md")
    m = page.meta
    owner = mc.norm(m.get("owner"))
    if user.get("role") != "manager" and owner != user["id"]:
        raise ValueError(f"{acc} is owned by {owner or 'nobody'}, not you (rules 6, 16)")
    prods = [p.strip() for p in products.split(";") if p.strip()]
    unknown = sorted(set(prods) - lint.product_ids(root))
    if unknown:
        raise ValueError(f"not in knowledge/products/: {', '.join(unknown)} (rule 4)")
    if ref and not (root / ref).is_file():
        raise ValueError(f"--ref file not found: {ref}")
    email = next((mc.norm(r.get("email")) for r in mc.load_reps(root) if r["id"] == owner), "")
    nxt = mc.norm(m.get("next_action"))
    due = mc.to_date(m.get("next_action_due"))
    values = {"Account Name": mc.norm(m.get("name")) or acc, "Stage": mc.norm(m.get("stage")),
              "Next Step": f"{nxt} by {due.isoformat()}" if nxt and due else nxt,
              "Owner Email": email, "Notes": " ".join(notes.split())}
    cols = columns(root)
    row = {c: values.get(c, "") for c in cols}
    touch = {"ts": mc.now_stamp(), "rep": owner or user["id"], "account": acc, "contact": contact,
             "channel": "meeting", "step": "meeting", "pattern": "", "products": ";".join(prods),
             "status": "meeting_held", "reply_class": "", "ref": ref}
    crm = root / "log" / "crm-updates" / f"{mc.today().isoformat()}.csv"
    if not dry_run:
        if crm.is_file() and crm.stat().st_size:
            with open(crm, encoding="utf-8-sig", newline="") as fh:
                header = next(csv.reader(fh), [])
            if [h.strip() for h in header] != cols:
                raise ValueError(f"{mc.rel_posix(crm, root)} header {header} differs from crm_mapping.yaml {cols}")
        mc.append_csv(crm, row, cols)
        mc.append_csv(root / "log" / "touches.csv", touch, mc.TOUCH_FIELDS)
    buf = io.StringIO()
    csv.DictWriter(buf, fieldnames=cols, lineterminator="\n").writerow(row)
    return {"crm_file": mc.rel_posix(crm, root), "columns": cols, "row": row, "csv_line": buf.getvalue().rstrip("\n"),
            "touch": touch, "written": not dry_run}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Append the CRM update row and meeting touch for an owned account.")
    ap.add_argument("--id", required=True, help="account id")
    ap.add_argument("--notes", required=True, help="one-line summary, no personal data")
    ap.add_argument("--contact", default="", help="main attendee contact id")
    ap.add_argument("--products", default="", help="product ids discussed, ';'-joined")
    ap.add_argument("--ref", default="", help="raw/notes/... file")
    ap.add_argument("--dry-run", action="store_true", help="print the row, write nothing")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    user = mc.current_user(root)
    if not user:
        print("Unknown user: run mama-setup first.")
        return 1
    try:
        res = handover(root, user, args.id, args.notes, args.contact, args.products, args.ref, args.dry_run)
    except ValueError as exc:
        print(f"Refused: {exc}")
        return 1
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
