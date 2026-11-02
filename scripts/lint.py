"""Mechanical lint for the Sales Mama wiki (Phase 0 checks).

Checks (E = error, W = warning):
  schema       E bad/missing frontmatter, wrong type for its folder, bad stage
               W keys missing vs templates/<type>.md, unknown keys, id != filename
  market       E account without a valid `market` (SG | MY | IN)
  registry     E reg_id format wrong for reg_type (uen, ssm, cin, llpin, gstin,
                 udyam), reg_type not allowed in the market;  W reg_id w/o reg_type
  ontology     E tags not in knowledge/ontology.yaml (only for categories that
                 have entries)
  products     E `recommended` ids not in knowledge/products/;  W products_owned
                 (only when knowledge/products/ has files)
  owners       E owner / allocated_by not a known rep;  W owner is inactive
  reps         E duplicate rep id/email, bad role;  W missing email
  links        W broken [[links]]
  contacts     W orphan contacts (no account, or the account page is missing)
  claims       W idle claims: owned, active, no touch for > 21 days
  actions      W overdue next_action_due on active accounts
  signals      E '## Signals' bullets without a raw/ link;  W cited raw file missing
  retention    W raw files older than guardrails.md 'Retention' (e.g. '- raw/signals: 180')
  suppression  E open drafts to suppressed contacts/domains;  W active contacts
                 that are suppressed
  skills       E .claude/skills out of sync with .agents/skills
  dedupe       W same registry id or domain twice within a market

Missing or empty knowledge files and an empty wiki are fine (exit 0).
Exit 1 only when there are errors. Env MAMA_TODAY=YYYY-MM-DD fixes "today".

    python3 scripts/lint.py
    python3 scripts/lint.py --json        # for mama-weekly
    python3 scripts/lint.py --errors-only
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402

IDLE_DAYS = 21
FOLDER_TYPES = {
    "wiki/accounts/": "account",
    "wiki/contacts/": "contact",
    "wiki/events/": "event",
    "wiki/responses/objections/": "objection",
    "wiki/responses/patterns/": "pattern",
    "wiki/responses/faq/": "faq",
}
REG_PATTERNS = mc.REG_PATTERNS
DEFAULT_ID_TYPES = mc.DEFAULT_ID_TYPES
ROLES = ("rep", "manager", "inactive")
LINK_RE = re.compile(r"\[\[([^\]\n]+)\]\]")
MD_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
PLACEHOLDER_BULLETS = {"unknown", "none", "none yet", "n/a", "-"}
# Template keys added later; older pages may lack them without a warning.
OPTIONAL_KEYS = {"contact": {"whatsapp", "whatsapp_opt_in_date", "whatsapp_opt_in_source"}}


class Report:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, level: str, check: str, path: str, msg: str) -> None:
        self.items.append({"level": level, "check": check, "path": path, "message": msg})

    def err(self, check, path, msg):
        self.add("error", check, path, msg)

    def warn(self, check, path, msg):
        self.add("warning", check, path, msg)

    @property
    def errors(self):
        return [i for i in self.items if i["level"] == "error"]

    @property
    def warnings(self):
        return [i for i in self.items if i["level"] == "warning"]


# ----------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------
def template_keys(root: Path) -> dict[str, list[str]]:
    out = {}
    folder = root / "templates"
    for p in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        page = mc.read_page(p, root)
        if page and isinstance(page.meta, dict):
            out[mc.norm(page.meta.get("type")) or p.stem] = list(page.meta.keys())
    return out


def ontology_terms(root: Path, rep: Report) -> dict[str, set[str]]:
    errs: list[str] = []
    data = mc.load_yaml(root / "knowledge" / "ontology.yaml", {}, errs)
    for e in errs:
        rep.err("ontology", "knowledge/ontology.yaml", f"cannot parse: {e}")
    if not isinstance(data, dict):
        return {}
    out = {}
    for key in ("industries", "signals", "pains", "personas"):
        v = data.get(key)
        terms = {str(x) for x in mc.as_list(v)} if v else set()
        if terms:
            out[key] = terms
    return out


def product_ids(root: Path) -> set[str]:
    folder = root / "knowledge" / "products"
    ids: set[str] = set()
    if not folder.is_dir():
        return ids
    for p in folder.iterdir():
        if p.suffix.lower() not in (".yaml", ".yml") or p.name.startswith("."):
            continue
        ids.add(p.stem)
        data = mc.load_yaml(p, {})
        if isinstance(data, dict) and mc.norm(data.get("id")):
            ids.add(mc.norm(data.get("id")))
    return ids


def market_id_types(root: Path) -> dict[str, list[str]]:
    data = mc.load_yaml(root / "knowledge" / "markets.yaml", {})
    out = {k: list(v) for k, v in DEFAULT_ID_TYPES.items()}
    if isinstance(data, dict) and isinstance(data.get("markets"), dict):
        for m, cfg in data["markets"].items():
            if isinstance(cfg, dict) and cfg.get("id_types"):
                out[str(m)] = [str(x).lower() for x in mc.as_list(cfg["id_types"])]
    return out


def collect_pages(root: Path, rep: Report) -> list[mc.Page]:
    """All wiki pages except generated ones and wiki/log.md; reports pages in
    typed folders that have no or broken frontmatter."""
    pages = []
    wiki = root / "wiki"
    if not wiki.is_dir():
        return pages
    for path in sorted(wiki.rglob("*.md")):
        rel = mc.rel_posix(path, root)
        if rel in ("wiki/index.md", "wiki/log.md") or rel.startswith("wiki/books/"):
            continue
        page = mc.read_page(path, root)
        if page is None:
            rep.err("schema", rel, "cannot read file")
            continue
        typed = any(rel.startswith(f) for f in FOLDER_TYPES)
        if page.meta is None:
            if page.error:
                rep.err("schema", rel, page.error)
            elif typed:
                rep.err("schema", rel, "no frontmatter (copy it from templates/)")
            continue
        pages.append(page)
    return pages


# ----------------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------------
def check_schema(pages, reps_pages, tmpl, rep: Report) -> None:
    for page in pages + reps_pages:
        m = page.meta
        expected = next((t for f, t in FOLDER_TYPES.items() if page.rel.startswith(f)), None)
        if page.rel.startswith("reps/"):
            expected = "rep"
        ptype = page.type
        if not ptype:
            rep.err("schema", page.rel, f"frontmatter has no `type`"
                    + (f" (expected `{expected}`)" if expected else ""))
            ptype = expected or ""
        elif expected and ptype != expected:
            rep.err("schema", page.rel, f"type `{ptype}` in a {expected} folder")
        if ptype in tmpl:
            keys = tmpl[ptype]
            missing = [k for k in keys if k not in m and k not in OPTIONAL_KEYS.get(ptype, ())]
            extra = [k for k in m if k not in keys]
            if missing:
                rep.warn("schema", page.rel, f"missing keys vs templates/{ptype}.md: {', '.join(missing)}")
            if extra:
                rep.warn("schema", page.rel, f"keys not in templates/{ptype}.md: {', '.join(map(str, extra))}")
        if "id" in m and mc.norm(m.get("id")) and mc.norm(m.get("id")) != page.path.stem:
            rep.warn("schema", page.rel, f"id `{mc.norm(m.get('id'))}` does not match file name")
        if "id" in m and not mc.norm(m.get("id")):
            rep.warn("schema", page.rel, "id is empty")
        if ptype == "account":
            stage = mc.norm(m.get("stage"))
            if stage and stage not in mc.STAGES:
                rep.err("schema", page.rel, f"unknown stage `{stage}` (allowed: {', '.join(mc.STAGES)})")
            tier = mc.norm(m.get("tier"))
            if tier and tier.upper() not in mc.TIERS:
                rep.warn("schema", page.rel, f"tier `{tier}` is not A, B or C")
        if ptype in ("objection", "pattern", "faq"):
            st = mc.norm(m.get("status"))
            if st and st not in ("draft", "approved", "retired"):
                rep.warn("schema", page.rel, f"status `{st}` is not draft | approved | retired")


def check_markets_and_ids(accounts, id_types, rep: Report) -> None:
    seen_reg: dict[tuple, str] = {}
    seen_dom: dict[tuple, str] = {}
    for page in accounts:
        m = page.meta
        market = mc.norm(m.get("market")).upper()
        if not market:
            rep.err("market", page.rel, "`market` is not set (SG | MY | IN)")
        elif market not in id_types:
            rep.err("market", page.rel, f"`market` is `{m.get('market')}`; use SG, MY or IN")
        reg_type = mc.norm(m.get("reg_type")).lower()
        reg_id = mc.norm(m.get("reg_id"))
        if reg_id and not reg_type:
            rep.warn("registry", page.rel, "reg_id is set but reg_type is empty")
        if reg_type:
            if reg_type not in REG_PATTERNS:
                rep.err("registry", page.rel, f"unknown reg_type `{reg_type}` "
                        f"(use {', '.join(REG_PATTERNS)})")
            elif market in id_types and reg_type not in id_types[market]:
                rep.err("registry", page.rel, f"reg_type `{reg_type}` is not used in {market} "
                        f"(allowed: {', '.join(id_types[market])})")
        if reg_id and reg_type in REG_PATTERNS:
            pat, human = REG_PATTERNS[reg_type]
            if not pat.match(reg_id.upper()):
                rep.err("registry", page.rel, f"reg_id `{reg_id}` is not a valid {reg_type.upper()} ({human})")
            key = (market, reg_type, reg_id.upper())
            if key in seen_reg:
                rep.warn("dedupe", page.rel, f"same {reg_type.upper()} as {seen_reg[key]}")
            else:
                seen_reg[key] = page.rel
        alt = m.get("alt_ids")
        if isinstance(alt, dict):
            for k, v in alt.items():
                k2, v2 = str(k).lower(), mc.norm(v)
                if v2 and k2 in REG_PATTERNS and not REG_PATTERNS[k2][0].match(v2.upper()):
                    rep.err("registry", page.rel, f"alt_ids.{k2} `{v2}` is not a valid "
                            f"{k2.upper()} ({REG_PATTERNS[k2][1]})")
        elif alt not in (None, "", {}):
            rep.warn("schema", page.rel, "alt_ids should be a mapping, e.g. {gstin: ...}")
        dom = mc.norm(m.get("domain")).lower().removeprefix("www.")
        if dom:
            key = (market, dom)
            if key in seen_dom:
                rep.warn("dedupe", page.rel, f"same domain `{dom}` as {seen_dom[key]}")
            else:
                seen_dom[key] = page.rel


def check_ontology(pages, onto: dict[str, set[str]], rep: Report) -> None:
    if not onto:
        return
    fields = {
        "account": {"industry": "industries", "signals": "signals", "pains": "pains"},
        "contact": {"persona": "personas"},
        "event": {"industries": "industries"},
        "objection": {"personas": "personas"},
        "pattern": {"personas": "personas", "pains": "pains", "signals": "signals"},
    }
    for page in pages:
        for field, cat in fields.get(page.type, {}).items():
            if cat not in onto:
                continue
            bad = [str(v) for v in mc.as_list(page.meta.get(field)) if str(v) not in onto[cat]]
            if bad:
                rep.err("ontology", page.rel, f"{field}: {', '.join(bad)} not in ontology.yaml "
                        f"{cat} (log as `unmapped` instead)")


def check_products(accounts, products: set[str], rep: Report) -> None:
    if not products:
        return
    for page in accounts:
        bad = [str(v) for v in mc.as_list(page.meta.get("recommended")) if str(v) not in products]
        if bad:
            rep.err("products", page.rel, f"recommended: {', '.join(bad)} not in knowledge/products/")
        bad = [str(v) for v in mc.as_list(page.meta.get("products_owned")) if str(v) not in products]
        if bad:
            rep.warn("products", page.rel, f"products_owned: {', '.join(bad)} not in knowledge/products/ "
                     "(map them in crm_mapping.yaml product_values)")


def check_reps(reps_pages, rep: Report) -> dict[str, dict]:
    known: dict[str, dict] = {}
    emails: dict[str, str] = {}
    for page in reps_pages:
        m = page.meta
        rid = mc.norm(m.get("id")) or page.path.stem
        if rid in known:
            rep.err("reps", page.rel, f"duplicate rep id `{rid}`")
        known[rid] = m
        role = mc.norm(m.get("role"))
        if role not in ROLES:
            rep.err("reps", page.rel, f"role `{role or '(empty)'}` must be rep, manager or inactive")
        email = mc.norm(m.get("email")).lower()
        if not email:
            rep.warn("reps", page.rel, "email is empty, so this person cannot be identified")
        elif email in emails:
            rep.err("reps", page.rel, f"email {email} is also used by {emails[email]}")
        else:
            emails[email] = page.rel
        for mk in mc.as_list(m.get("markets")):
            if str(mk).upper() not in mc.MARKETS:
                rep.warn("reps", page.rel, f"market `{mk}` is not SG, MY or IN")
    return known


def check_owners(accounts, known: dict[str, dict], rep: Report) -> None:
    for page in accounts:
        for field in ("owner", "allocated_by"):
            v = mc.norm(page.meta.get(field))
            if not v:
                continue
            if v not in known:
                rep.err("owners", page.rel, f"{field} `{v}` is not a known rep (reps/{v}.md missing)")
            elif field == "owner" and mc.norm(known[v].get("role")) == "inactive" \
                    and mc.is_active(page.meta):
                rep.warn("owners", page.rel, f"owner `{v}` is inactive; reassign with claim.py --reassign")


def _link_target(target: str, root: Path) -> Path:
    t = target.split("|")[0].split("#")[0].strip()
    t = re.sub(r"\.md$", "", t)
    if t.startswith("wiki/"):
        t = t[5:]
    return root / "wiki" / f"{t}.md"


def check_links(pages, root: Path, rep: Report) -> None:
    for page in pages:
        text = mc.strip_comments(page.text)
        missing = sorted({t for t in LINK_RE.findall(text) if not _link_target(t, root).is_file()})
        if missing:
            rep.warn("links", page.rel, "broken link(s): " + ", ".join(f"[[{t}]]" for t in missing))


def check_contacts(contacts, account_ids: set[str], rep: Report) -> None:
    for page in contacts:
        acc = mc.link_id(page.meta.get("account"))
        if not acc:
            rep.warn("contacts", page.rel, "orphan contact: `account` is empty")
        elif acc not in account_ids:
            rep.warn("contacts", page.rel, f"orphan contact: account `{acc}` has no page")


def last_touch_dates(touches: list[dict]) -> dict[str, dt.date]:
    out: dict[str, dt.date] = {}
    for t in touches:
        acc = mc.link_id(t.get("account"))
        d = mc.to_date(t.get("ts"))
        if acc and d and (acc not in out or d > out[acc]):
            out[acc] = d
    return out


def check_claims_and_actions(accounts, touches, on: dt.date, rep: Report) -> None:
    last = last_touch_dates(touches)
    for page in accounts:
        m = page.meta
        if not mc.is_active(m):
            continue
        due = mc.to_date(m.get("next_action_due"))
        if due and due < on:
            rep.warn("actions", page.rel, f"next action overdue since {due.isoformat()}: "
                     f"{mc.norm(m.get('next_action')) or '(no next_action text)'}")
        if not mc.norm(m.get("owner")):
            continue
        claimed = [d for d in (mc.to_date(m.get("claimed_on")), mc.to_date(m.get("allocated_on"))) if d]
        if not claimed:
            continue
        ref = max(claimed + [d for d in (mc.to_date(m.get("last_touch")), last.get(page.id)) if d])
        if (on - ref).days > IDLE_DAYS:
            rep.warn("claims", page.rel, f"idle claim: owned by {m.get('owner')}, no touch for "
                     f"{(on - ref).days} days (> {IDLE_DAYS}); release or reassign")


def check_signals(accounts, root: Path, rep: Report) -> None:
    for page in accounts:
        sec = mc.section(page.body, "Signals")
        for line in sec.splitlines():
            s = line.strip()
            if not re.match(r"^[-*+]\s+", s):
                continue
            content = re.sub(r"^[-*+]\s+", "", s).strip()
            if content.lower().rstrip(".") in PLACEHOLDER_BULLETS:
                continue
            raws = [u for u in MD_LINK_RE.findall(content) if "raw/" in u]
            raws += [w for w in re.findall(r"(?<![\w/])(raw/[^\s)\]>]+)", content) if w not in raws]
            if not raws:
                rep.err("signals", page.rel, f"Signals bullet without a raw/ source link: "
                        f"\"{content[:70]}\"")
                continue
            for u in raws:
                rel = u[u.index("raw/"):].split("#")[0].rstrip(".,;")
                if not (root / rel).exists():
                    rep.warn("signals", page.rel, f"cited raw file not found: {rel}")


def retention_rules(root: Path) -> dict[str, int]:
    path = root / "knowledge" / "guardrails.md"
    if not path.is_file():
        return {}
    text = mc.strip_comments(mc.read_text(path))
    sec = mc.section(text, "Retention") or ""
    rules = {}
    for line in sec.splitlines():
        m = re.match(r"^\s*[-*]\s*`?(raw/[\w./-]+?)/?`?\s*[:=]\s*(\d+)", line)
        if m:
            rules[m.group(1).rstrip("/")] = int(m.group(2))
    return rules


def _file_date(p: Path, root: Path) -> dt.date | None:
    rel = mc.rel_posix(p, root)
    found = re.findall(r"(\d{4}-\d{2}-\d{2})", rel)
    if found:
        return mc.to_date(found[-1])
    try:
        return dt.date.fromtimestamp(p.stat().st_mtime)
    except OSError:
        return None


def check_retention(root: Path, on: dt.date, rep: Report) -> None:
    for folder, days in retention_rules(root).items():
        base = root / folder
        if not base.is_dir():
            continue
        expired = []
        for p in base.rglob("*"):
            if not p.is_file() or p.name == ".gitkeep":
                continue
            d = _file_date(p, root)
            if d and (on - d).days > days:
                expired.append(mc.rel_posix(p, root))
        if expired:
            rep.warn("retention", folder, f"{len(expired)} file(s) older than {days} days "
                     f"(manager approves deletion in mama-weekly), e.g. {expired[0]}")


def check_suppression(root: Path, contacts, touches, rep: Report) -> None:
    rows = mc.read_csv(root / "wiki" / "suppression.csv")
    emails = {r["value"].lower() for r in rows
              if r.get("value") and (r.get("type", "").lower() == "email" or "@" in r["value"])}
    domains = {r["value"].lower().lstrip("@") for r in rows
               if r.get("value") and r.get("type", "").lower() == "domain"}
    if not emails and not domains:
        return

    def suppressed(email: str) -> bool:
        e = email.lower().strip()
        return bool(e) and (e in emails or e.split("@")[-1] in domains)

    contact_email = {}
    for page in contacts:
        email = mc.norm(page.meta.get("email"))
        contact_email[page.id] = email
        if suppressed(email) and mc.norm(page.meta.get("status")) != "do_not_contact":
            rep.warn("suppression", page.rel, f"{email} is suppressed but status is "
                     f"`{mc.norm(page.meta.get('status')) or 'active'}`; set do_not_contact")
    latest: dict[tuple, dict] = {}
    for t in touches:
        key = (mc.link_id(t.get("account")), mc.link_id(t.get("contact"), "contacts"), t.get("step", ""))
        latest[key] = t  # rows are append-only: the last one wins
    for (acc, contact, step), t in latest.items():
        if mc.norm(t.get("status")) != "drafted":
            continue
        email = contact if "@" in contact else contact_email.get(contact, "")
        if suppressed(email):
            rep.err("suppression", "log/touches.csv", f"open draft ({step or 'step?'}) to suppressed "
                    f"contact {email} on {acc}: delete the mailbox draft")


def check_secrets(root: Path, rep: Report) -> None:
    """Secrets files or token strings in tracked files (ADR-0007: secrets live in ~/.config/sales-mama/)."""
    from guard import SECRET_NAME_RE, SECRET_RE
    code, out, _ = mc.run_git(["ls-files", "--cached", "--others", "--exclude-standard"], cwd=root, timeout=30)
    files = [ln for ln in out.splitlines() if ln.strip()] if code == 0 else \
        [mc.rel_posix(p, root) for p in root.rglob("*") if p.is_file() and ".git" not in p.parts
         and "node_modules" not in p.parts]
    for rel in files:
        p = root / rel
        if SECRET_NAME_RE.search(rel):
            rep.err("secrets", rel, "secrets file in the repo: move it to ~/.config/sales-mama/ and rotate it")
            continue
        try:
            if not p.is_file() or p.stat().st_size > 1_000_000:
                continue
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if SECRET_RE.search(text):
            rep.err("secrets", rel, "contains what looks like a token or private key: remove it and rotate it")


def check_skills(root: Path, rep: Report) -> None:
    try:
        import sync_skills
        drift = sync_skills.check(root)
    except Exception as exc:  # noqa: BLE001
        rep.warn("skills", ".claude/skills", f"could not check the mirror: {exc}")
        return
    for line in drift[:10]:
        rep.err("skills", ".claude/skills", f"{line} (run python3 scripts/sync_skills.py)")
    if len(drift) > 10:
        rep.err("skills", ".claude/skills", f"+{len(drift) - 10} more differences")


# ----------------------------------------------------------------------------
def run(root: Path) -> Report:
    rep = Report()
    on = mc.today()
    tmpl = template_keys(root)
    pages = collect_pages(root, rep)
    reps_pages = []
    for p in sorted((root / "reps").glob("*.md")) if (root / "reps").is_dir() else []:
        page = mc.read_page(p, root)
        if page is None or page.meta is None:
            rep.err("schema", mc.rel_posix(p, root), (page.error if page else None) or "no frontmatter")
            continue
        reps_pages.append(page)

    accounts = [p for p in pages if p.type == "account"]
    contacts = [p for p in pages if p.type == "contact"]
    touches = mc.load_touches(root)

    check_schema(pages, reps_pages, tmpl, rep)
    check_markets_and_ids(accounts, market_id_types(root), rep)
    check_ontology(pages, ontology_terms(root, rep), rep)
    check_products(accounts, product_ids(root), rep)
    known = check_reps(reps_pages, rep)
    check_owners(accounts, known, rep)
    check_links(pages + reps_pages, root, rep)
    check_contacts(contacts, {p.id for p in accounts}, rep)
    check_claims_and_actions(accounts, touches, on, rep)
    check_signals(accounts, root, rep)
    check_retention(root, on, rep)
    check_suppression(root, contacts, touches, rep)
    check_secrets(root, rep)
    check_skills(root, rep)
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Lint the Sales Mama wiki. Exit 1 only on errors.")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--errors-only", action="store_true", help="hide warnings")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(f"lint.py: {mc.YAML_MISSING}")
        return 1
    root = mc.repo_root()
    rep = run(root)
    items = rep.errors if args.errors_only else rep.items
    if args.json:
        print(json.dumps({
            "date": mc.today().isoformat(), "ok": not rep.errors,
            "errors": len(rep.errors), "warnings": len(rep.warnings), "items": items,
        }, indent=2, ensure_ascii=False))
    else:
        by_check = defaultdict(list)
        for i in items:
            by_check[i["check"]].append(i)
        for check in sorted(by_check):
            for i in by_check[check]:
                tag = "ERROR" if i["level"] == "error" else "warn "
                print(f"{tag} [{check}] {i['path']}: {i['message']}")
        print(f"lint: {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)"
              + (" — OK" if not rep.errors else ""))
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
