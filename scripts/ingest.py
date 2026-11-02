"""Deterministic CRM ingest for mama-ingest (Phase 1).

Maps a CRM export in raw/crm/ with knowledge/crm_mapping.yaml and creates or
updates wiki/accounts/ pages. Manager only.

- Columns: `export:` (CSV column -> account field; dotted targets such as
  `alt_ids.gstin`). Values: `country_values` (-> SG | MY | IN),
  `industry_values` (-> ontology term), `product_values` (-> product id,
  cells split on ";"). Optional `date_formats` (default ISO, then DD/MM/YYYY).
- Unknown industry or product values are left blank and logged once as
  `unmapped` (AGENTS.md rule 7). Rows whose country does not map are skipped.
- reg_type is inferred from the market's id_types in markets.yaml; an ID that
  matches none of them is left blank and reported.
- Dedupe within a market: registry ID -> domain -> normalised name + city,
  against existing pages and earlier rows of the same file.
- Existing accounts: only CRM-owned fields change, never owner, stage or
  next_action. Empty cells never blank an existing value.
- New accounts: from templates/account.md, `source: crm`, `stage: new`, no
  owner. Every touched page cites the export in `## Snapshot` (rule 3).
- propensity: kept if all values <= 1, else /100 if all <= 100, else /max.
- Contract ends within 120 days are listed as `contract_ending` candidates.
  They are NOT written to log/signals.csv: only resolve.py (Phase 2) links
  signals (rule 10).
- raw/ is never written. A file already named in a wiki/log.md ingest line is
  skipped unless --force.

    python3 scripts/ingest.py crm raw/crm/2026-11-01-export.csv --dry-run
    python3 scripts/ingest.py crm raw/crm/2026-11-01-export.csv
    python3 scripts/ingest.py crm raw/crm/2026-11-01-export.csv --json

Exit 0 on success (or skipped), 1 when refused or the file cannot be read.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402

CRM_FIELDS = ("name", "market", "reg_type", "reg_id", "alt_ids", "domain", "city", "group",
              "industry", "employees", "products_owned", "contract_end", "propensity")
CONTRACT_WINDOW_DAYS = 120
DEFAULT_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y")


# ----------------------------------------------------------------------------
# Knowledge
# ----------------------------------------------------------------------------
def market_id_types(root: Path) -> dict[str, list[str]]:
    data = mc.load_yaml(root / "knowledge" / "markets.yaml", {})
    out = {k: list(v) for k, v in mc.DEFAULT_ID_TYPES.items()}
    if isinstance(data, dict) and isinstance(data.get("markets"), dict):
        for m, cfg in data["markets"].items():
            if isinstance(cfg, dict) and cfg.get("id_types"):
                out[str(m)] = [str(x).lower() for x in mc.as_list(cfg["id_types"])]
    return out


def ontology_industries(root: Path) -> set[str]:
    data = mc.load_yaml(root / "knowledge" / "ontology.yaml", {})
    return {str(x) for x in mc.as_list(data.get("industries"))} if isinstance(data, dict) else set()


def product_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    folder = root / "knowledge" / "products"
    for p in sorted(folder.glob("*.y*ml")) if folder.is_dir() else []:
        ids.add(p.stem)
        data = mc.load_yaml(p, {})
        if isinstance(data, dict) and mc.norm(data.get("id")):
            ids.add(mc.norm(data["id"]))
    return ids


def ci_lookup(table: dict, value: str) -> str:
    """Case-insensitive lookup in a CRM value map; '' if absent."""
    v = value.strip().lower()
    for k, out in (table or {}).items():
        if str(k).strip().lower() == v:
            return mc.norm(out)
    return ""


# ----------------------------------------------------------------------------
# Values
# ----------------------------------------------------------------------------
def norm_domain(value: str) -> str:
    d = value.strip().lower()
    d = re.sub(r"^[a-z]+://", "", d).split("/")[0].split("?")[0]
    return d.removeprefix("www.")


def parse_date(value: str, formats) -> dt.date | None:
    for fmt in formats:
        try:
            return dt.datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_int(value: str) -> int | None:
    v = value.replace(",", "").strip()
    try:
        return int(float(v))
    except ValueError:
        return None


def parse_float(value: str) -> float | None:
    try:
        return float(value.replace("%", "").strip())
    except ValueError:
        return None


def name_key(name: str) -> str:
    return mc.legal_slug(name)


def same(a, b) -> bool:
    if isinstance(a, list) or isinstance(b, list):
        return [str(x) for x in mc.as_list(a)] == [str(x) for x in mc.as_list(b)]
    if isinstance(a, dict) or isinstance(b, dict):
        return {str(k): mc.norm(v) for k, v in (a or {}).items()} == \
               {str(k): mc.norm(v) for k, v in (b or {}).items()}
    return mc.norm(a) == mc.norm(b)


# ----------------------------------------------------------------------------
# Page body
# ----------------------------------------------------------------------------
def add_to_section(body: str, heading: str, line: str) -> str:
    """Append `line` at the end of '## heading' (before the next heading)."""
    lines = body.split("\n")
    start = next((i for i, ln in enumerate(lines)
                  if re.match(rf"^##\s+{re.escape(heading)}\b", ln, re.I)), None)
    if start is None:
        return body.rstrip("\n") + f"\n## {heading}\n{line}\n"
    end = start + 1
    while end < len(lines) and not re.match(r"^#{1,2}\s", lines[end]):
        end += 1
    insert = end
    while insert > start + 1 and lines[insert - 1].strip() == "":
        insert -= 1
    lines.insert(insert, line)
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Ingest
# ----------------------------------------------------------------------------
class Result:
    def __init__(self, file: str):
        self.file = file
        self.rows = 0
        self.new: list[str] = []
        self.updated: list[str] = []
        self.unchanged: list[str] = []
        self.duplicates: list[dict] = []
        self.skipped: list[dict] = []
        self.issues: list[dict] = []
        self.unmapped: dict[str, set[str]] = {"industry": set(), "product": set()}
        self.contract_ending: list[dict] = []

    def as_dict(self) -> dict:
        return {
            "file": self.file, "rows": self.rows, "new": self.new, "updated": self.updated,
            "unchanged": self.unchanged, "duplicates": self.duplicates, "skipped": self.skipped,
            "issues": self.issues,
            "unmapped": {k: sorted(v) for k, v in self.unmapped.items()},
            "contract_ending": self.contract_ending,
        }

    def summary(self) -> str:
        n_unmapped = sum(len(v) for v in self.unmapped.values())
        return (f"{len(self.new)} new, {len(self.updated)} updated, {len(self.unchanged)} unchanged, "
                f"{len(self.duplicates)} dup, {len(self.skipped)} skipped, "
                f"{len(self.contract_ending)} contract_ending, {n_unmapped} unmapped")


def already_ingested(root: Path, rel: str) -> bool:
    log = root / "wiki" / "log.md"
    if not log.is_file():
        return False
    pat = re.compile(rf"\]\s*ingest\s*\|[^|]*\|\s*{re.escape(rel)}\s*\|")
    return any(pat.search(ln) for ln in mc.read_text(log).splitlines())


def map_row(row: dict, mapping: dict, ctx: dict, res: Result, lineno: int) -> dict | None:
    rec: dict = {"alt_ids": {}}
    for col, field in (mapping.get("export") or {}).items():
        val = mc.norm(row.get(str(col)))
        if not val:
            continue
        if "." in str(field):
            head, sub = str(field).split(".", 1)
            if head == "alt_ids":
                rec["alt_ids"][sub] = val
            continue
        rec[str(field)] = val

    name = rec.get("name", "")
    if not name:
        res.skipped.append({"row": lineno, "reason": "no account name"})
        return None
    raw_market = rec.get("market", "")
    market = ci_lookup(mapping.get("country_values") or {}, raw_market) or raw_market.upper()
    if market not in mc.MARKETS:
        res.skipped.append({"row": lineno, "name": name,
                            "reason": f"country `{raw_market}` does not map to SG | MY | IN"})
        return None
    rec["market"] = market

    reg = re.sub(r"\s+", "", rec.get("reg_id", "")).upper()
    rec["reg_id"], rec["reg_type"] = "", ""
    if reg:
        for t in ctx["id_types"].get(market, []):
            if t in mc.REG_PATTERNS and mc.REG_PATTERNS[t][0].match(reg):
                rec["reg_id"], rec["reg_type"] = reg, t
                break
        else:
            res.issues.append({"row": lineno, "name": name,
                               "issue": f"reg_id `{reg}` is not a valid {'/'.join(ctx['id_types'].get(market, []))} "
                                        "for this market; left blank"})
    alt = {}
    for k, v in rec["alt_ids"].items():
        v2 = re.sub(r"\s+", "", v).upper()
        if k in mc.REG_PATTERNS and not mc.REG_PATTERNS[k][0].match(v2):
            res.issues.append({"row": lineno, "name": name, "issue": f"alt_ids.{k} `{v}` is not valid; dropped"})
            continue
        alt[k] = v2
    rec["alt_ids"] = alt

    if rec.get("domain"):
        rec["domain"] = norm_domain(rec["domain"])

    if rec.get("industry"):
        raw = rec["industry"]
        term = ci_lookup(mapping.get("industry_values") or {}, raw)
        if not term and raw in ctx["industries"]:
            term = raw
        if term and ctx["industries"] and term not in ctx["industries"]:
            term = ""
        if not term:
            res.unmapped["industry"].add(raw)
        rec["industry"] = term

    if rec.get("products_owned"):
        out = []
        for raw in [p.strip() for p in rec["products_owned"].split(";") if p.strip()]:
            pid = ci_lookup(mapping.get("product_values") or {}, raw)
            if not pid and raw in ctx["products"]:
                pid = raw
            if pid and ctx["products"] and pid not in ctx["products"]:
                pid = ""
            if pid:
                if pid not in out:
                    out.append(pid)
            else:
                res.unmapped["product"].add(raw)
        rec["products_owned"] = out

    if rec.get("employees"):
        emp = parse_int(rec["employees"])
        if emp is None:
            res.issues.append({"row": lineno, "name": name, "issue": f"employees `{rec['employees']}` is not a number"})
        rec["employees"] = emp

    if rec.get("contract_end"):
        d = parse_date(rec["contract_end"], ctx["date_formats"])
        if d is None:
            res.issues.append({"row": lineno, "name": name,
                               "issue": f"contract_end `{rec['contract_end']}` is not a date; left blank"})
        rec["contract_end"] = d

    if rec.get("propensity"):
        rec["propensity"] = parse_float(rec["propensity"])
    return rec


def normalise_propensity(recs: list[dict]) -> None:
    vals = [r["propensity"] for r in recs if isinstance(r.get("propensity"), (int, float))]
    if not vals:
        return
    top = max(vals)
    div = 1.0 if top <= 1 else (100.0 if top <= 100 else top)
    for r in recs:
        if isinstance(r.get("propensity"), (int, float)):
            r["propensity"] = round(max(0.0, r["propensity"]) / div, 2)


class Index:
    """Dedupe keys -> account id, within a market."""

    def __init__(self):
        self.reg: dict[tuple, str] = {}
        self.dom: dict[tuple, str] = {}
        self.name: dict[tuple, str] = {}
        self.ids: set[str] = set()

    def add(self, aid: str, meta: dict) -> None:
        self.ids.add(aid)
        market = mc.norm(meta.get("market")).upper()
        reg = mc.norm(meta.get("reg_id")).upper()
        if reg:
            self.reg[(market, reg)] = aid
        for v in (meta.get("alt_ids") or {}).values() if isinstance(meta.get("alt_ids"), dict) else []:
            if mc.norm(v):
                self.reg[(market, mc.norm(v).upper())] = aid
        dom = norm_domain(mc.norm(meta.get("domain")))
        if dom:
            self.dom[(market, dom)] = aid
        if mc.norm(meta.get("name")):
            self.name[(market, name_key(meta["name"]), mc.norm(meta.get("city")).lower())] = aid

    def find(self, rec: dict) -> tuple[str, str] | None:
        m = rec["market"]
        for reg in [rec.get("reg_id")] + list(rec.get("alt_ids", {}).values()):
            if reg and (m, reg.upper()) in self.reg:
                return self.reg[(m, reg.upper())], "registry id"
        if rec.get("domain") and (m, rec["domain"]) in self.dom:
            return self.dom[(m, rec["domain"])], "domain"
        key = (m, name_key(rec["name"]), mc.norm(rec.get("city")).lower())
        if key in self.name:
            return self.name[key], "name + city"
        return None


def new_id(rec: dict, taken: set[str]) -> str:
    base = mc.legal_slug(rec["name"], rec["market"], taken)
    aid, n = base, 2
    while aid in taken:
        aid = f"{base}-{n}"
        n += 1
    return aid


def ingest_crm(root: Path, rel: str, user: str, dry_run: bool) -> Result:
    res = Result(rel)
    path = root / rel
    mapping = mc.load_yaml(root / "knowledge" / "crm_mapping.yaml", {}) or {}
    ctx = {
        "id_types": market_id_types(root),
        "industries": ontology_industries(root),
        "products": product_ids(root),
        "date_formats": mapping.get("date_formats") or ([mapping["date_format"]] if mapping.get("date_format")
                                                        else list(DEFAULT_DATE_FORMATS)),
    }
    rows = mc.read_csv(path)
    res.rows = len(rows)
    tmpl = mc.read_page(root / "templates" / "account.md", root)
    if tmpl is None or tmpl.meta is None:
        raise RuntimeError("templates/account.md is missing or has no frontmatter")

    idx = Index()
    pages: dict[str, mc.Page] = {}
    for page in mc.iter_pages("account", root):
        pages[page.id] = page
        idx.add(page.id, page.meta)

    recs = []
    for i, row in enumerate(rows, start=2):  # line 1 is the header
        rec = map_row(row, mapping, ctx, res, i)
        if rec:
            rec["_row"] = i
            recs.append(rec)
    normalise_propensity(recs)

    mapped_fields = {str(f).split(".")[0] for f in (mapping.get("export") or {}).values()}
    if "reg_id" in mapped_fields:
        mapped_fields.add("reg_type")
    on = mc.today()
    cite = f"- CRM fields from [crm export]({rel}) ({on.isoformat()})"
    touched: dict[str, int] = {}

    for rec in recs:
        hit = idx.find(rec)
        if hit and hit[0] in touched:
            res.duplicates.append({"row": rec["_row"], "name": rec["name"], "account": hit[0],
                                   "first_row": touched[hit[0]], "by": hit[1]})
            continue
        fields = {k: rec.get(k) for k in CRM_FIELDS if k in mapped_fields or k == "market"}
        if hit:
            aid = hit[0]
            page = mc.read_page(pages[aid].path, root)  # re-read right before editing (rule 17)
            meta = page.meta or {}
            changes = {}
            for k, v in fields.items():
                if v in (None, "", [], {}):
                    continue
                if k == "name" and name_key(v) == name_key(meta.get("name")):
                    continue  # "Pte. Ltd." vs "Pte Ltd" is not a change
                if k == "alt_ids":
                    v = {**(meta.get("alt_ids") or {}), **v} if isinstance(meta.get("alt_ids"), dict) else v
                if not same(meta.get(k), v):
                    changes[k] = v
            needs_cite = rel not in page.body
            if changes or needs_cite:
                res.updated.append(aid)
                if not dry_run:
                    if changes:
                        changes["updated"] = on
                        mc.update_frontmatter(page.path, changes)
                    if needs_cite:
                        fresh = mc.read_page(page.path, root)
                        mc.write_text(page.path, fresh.text[: len(fresh.text) - len(fresh.body)]
                                      + add_to_section(fresh.body, "Snapshot", cite))
            else:
                res.unchanged.append(aid)
            final = {**meta, **changes}
        else:
            aid = new_id(rec, idx.ids)
            meta = {k: (v.copy() if isinstance(v, (list, dict)) else v) for k, v in tmpl.meta.items()}
            for k, v in fields.items():
                if v not in (None, ""):
                    meta[k] = v
            meta.update({"type": "account", "id": aid, "source": "crm", "stage": "new",
                         "owner": None, "updated": on})
            body = tmpl.body.replace("{name}", rec["name"])
            body = add_to_section(body, "Snapshot", cite)
            res.new.append(aid)
            if not dry_run:
                mc.write_page(root / "wiki" / "accounts" / f"{aid}.md", meta, body)
            final = meta
        idx.add(aid, final)
        touched[aid] = rec["_row"]
        ce = mc.to_date(final.get("contract_end"))
        if ce and 0 <= (ce - on).days <= CONTRACT_WINDOW_DAYS:
            res.contract_ending.append({
                "account": aid, "company_text": rec["name"], "market": rec["market"],
                "contract_end": ce.isoformat(), "source": "crm-contracts", "source_type": "internal",
                "signal": "contract_ending", "snapshot": rel})

    if not dry_run:
        for kind, vals in res.unmapped.items():
            for v in sorted(vals):
                mc.append_log("unmapped", user, rel,
                              f"{kind} \"{v}\" has no mapping (crm_mapping.yaml {kind}_values)", root)
        mc.append_log("ingest", user, rel, res.summary(), root)
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ingest a CRM export from raw/crm/ into wiki/accounts/ "
                                             "(manager only).")
    sub = ap.add_subparsers(dest="kind", required=True)
    crm = sub.add_parser("crm", help="ingest one CRM export (CSV)")
    crm.add_argument("file", help="path to the export, e.g. raw/crm/2026-11-01-export.csv")
    crm.add_argument("--dry-run", action="store_true", help="show what would change; write nothing")
    crm.add_argument("--force", action="store_true", help="ingest even if the log says it was done")
    crm.add_argument("--json", action="store_true", help="print the result as JSON")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    user = mc.current_user(root)
    if not user or mc.norm(user.get("role")) != "manager":
        who = user.get("id") if user else (mc.git_email(root) or "unknown user")
        print(f"Refused: raw/crm/ ingest is manager only (AGENTS.md Operations); {who} is not a manager.")
        return 1
    path = Path(args.file)
    path = (path if path.is_absolute() else (Path.cwd() / path)).resolve()
    if not path.is_file():
        alt = (root / args.file).resolve()
        path = alt if alt.is_file() else path
    rel = mc.rel_posix(path, root)
    if not rel.startswith("raw/crm/") or not path.is_file():
        print(f"Not a file under raw/crm/: {args.file}")
        return 1
    if already_ingested(root, rel) and not args.force:
        msg = f"Skipped: {rel} is already ingested (see wiki/log.md); use --force to re-run."
        print(json.dumps({"file": rel, "skipped": True, "reason": msg}) if args.json else msg)
        return 0
    res = ingest_crm(root, rel, user["id"], args.dry_run)
    if args.json:
        out = res.as_dict()
        out["dry_run"] = args.dry_run
        print(json.dumps(out, indent=2, default=str))
        return 0
    print(f"{'DRY RUN — nothing written. ' if args.dry_run else ''}Ingested {rel}: {res.rows} rows → "
          f"{res.summary()}.")
    for d in res.duplicates:
        print(f"  dup      row {d['row']}: {d['name']} = {d['account']} (row {d['first_row']}, by {d['by']})")
    for s in res.skipped:
        print(f"  skipped  row {s['row']}: {s.get('name', '')} — {s['reason']}")
    for i in res.issues:
        print(f"  issue    row {i['row']}: {i['name']} — {i['issue']}")
    for kind, vals in res.unmapped.items():
        for v in sorted(vals):
            print(f"  unmapped {kind}: \"{v}\" → add it to crm_mapping.yaml {kind}_values")
    if res.contract_ending:
        print(f"  contract_ending candidates ({len(res.contract_ending)}, ≤ {CONTRACT_WINDOW_DAYS} days): "
              + ", ".join(f"{c['account']} ({c['contract_end']})" for c in res.contract_ending))
        resolver = root / "scripts" / "resolve.py"
        if not resolver.is_file():
            print("  → not linked yet: resolve.py arrives in Phase 2 (only it writes log/signals.csv).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
