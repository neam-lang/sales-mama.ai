"""Quality evals for Sales Mama (PLAN.md §16), run after every phase.

Each check reports PASS, FAIL or PENDING (not measurable yet: the phase that
enables it is named). Exit 1 only when a check FAILs.

Live from Phase 1:
  cited          account facts, Snapshot and Signals bullets cite an existing raw/ file (100%)
  catalog        `recommended` / `products_owned` ids exist in knowledge/products/
  suppression    no drafted touch to a suppressed contact or domain (0)
  golden         evals/golden_accounts/*.md parse, are accounts, have `## Expected`
  labelled       evals/labeled_*.csv headers match evals/README.md
  resolution     resolve.py auto-link precision >= 95% per live market (Phase 2;
                 PENDING until 50 labelled items per live market)
Live from Phase 3:
  recommendation golden accounts: recommend.py's top product and the page's
                 `recommended[0]` match the expected primary (>= 80%)
  entities       contacts on account pages are named in a cited raw/ file, and
                 golden `Must not` strings appear nowhere on the page (0)
Live from Phase 4 (over log/drafts/, saved by draft_check.py --save):
  send_window    saved drafts on a send day of the market (not a holiday), allowed channel (0)
  language       non-English drafts have an approved pattern in that language (0)
  draft_catalog  products in drafts and drafted touches exist in knowledge/products/ (0)
  fabrication    every name, number and date in a draft is on the account/contact page
                 or in knowledge/ (draft_check.py's entity check) (0)
  replies        classify_reply.py accuracy on evals/labeled_replies.csv (>= 90%;
                 PENDING under 40 rows)
  allocation     owned accounts inside their owner's market, territory and
                 max_active, and a dry-run allocate.py proposal passes every
                 hard-constraint check (0)
Pending until their phase:
  draft_quality (LLM judge, mama-weekly), vam_bounds (5),
  calibration (4+ weeks of touches).

    python3 scripts/eval.py
    python3 scripts/eval.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402

MD_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
RAW_RE = re.compile(r"(?<![\w/])(raw/[^\s)\]>]+)")
PLACEHOLDER_BULLETS = {"unknown", "none", "none yet", "n/a", "-"}
LABELLED_HEADERS = {
    "labeled_matches.csv": ["id", "market", "source", "company_text", "expected_account"],
    "labeled_replies.csv": ["id", "market", "lang", "text", "label"],
}
# Optional trailing columns (resolve.py reads them as match evidence).
LABELLED_OPTIONAL = {"labeled_matches.csv": ["reg_id", "domain", "city", "note"]}
RESOLUTION_MIN_ROWS = 50
RESOLUTION_TARGET = 0.95
REPLIES_MIN_ROWS = 40
REPLIES_TARGET = 0.90


class Check:
    def __init__(self, key: str, title: str, target: str):
        self.key, self.title, self.target = key, title, target
        self.status = "PENDING"
        self.value = ""
        self.details: list[str] = []

    def done(self, ok: bool, value: str, details: list[str] | None = None) -> "Check":
        self.status = "PASS" if ok else "FAIL"
        self.value = value
        self.details = details or []
        return self

    def pending(self, why: str) -> "Check":
        self.status, self.value = "PENDING", why
        return self

    def as_dict(self) -> dict:
        return {"key": self.key, "title": self.title, "target": self.target,
                "status": self.status, "value": self.value, "details": self.details}


def raw_links(text: str) -> list[str]:
    out = [u for u in MD_LINK_RE.findall(text) if "raw/" in u]
    out += [w for w in RAW_RE.findall(text) if w not in out]
    return [u[u.index("raw/"):].split("#")[0].rstrip(".,;") for u in out]


def has_crm_facts(meta: dict) -> bool:
    keys = ("reg_id", "domain", "city", "industry", "employees", "contract_end", "propensity")
    return any(meta.get(k) not in (None, "", [], {}) for k in keys) or bool(mc.as_list(meta.get("products_owned")))


# ----------------------------------------------------------------------------
# Live checks
# ----------------------------------------------------------------------------
def check_cited(root: Path, accounts: list[mc.Page]) -> Check:
    c = Check("cited", "Account claims and signals with a source link", "100%")
    total = good = 0
    bad: list[str] = []
    for page in accounts:
        for heading, kind in (("Snapshot", "snapshot"), ("Signals", "signal")):
            for line in mc.section(page.body, heading).splitlines():
                s = line.strip()
                if not re.match(r"^[-*+]\s+", s):
                    continue
                content = re.sub(r"^[-*+]\s+", "", s).strip()
                if content.lower().rstrip(".") in PLACEHOLDER_BULLETS or (
                        kind == "snapshot" and re.search(r"\bunknown\b", content, re.I) and not raw_links(content)):
                    continue
                total += 1
                links = raw_links(content)
                if links and all((root / u).exists() for u in links):
                    good += 1
                else:
                    bad.append(f"{page.rel}: {kind} \"{content[:60]}\"" + ("" if links else " (no raw/ link)"))
        if has_crm_facts(page.meta):
            total += 1
            links = [u for u in raw_links(page.body) if (root / u).exists()]
            if links:
                good += 1
            else:
                bad.append(f"{page.rel}: account facts without an existing raw/ source")
    if total == 0:
        return c.pending("no account claims yet")
    return c.done(good == total, f"{good}/{total} ({100 * good // total}%)", bad)


def product_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    folder = root / "knowledge" / "products"
    for p in sorted(folder.glob("*.y*ml")) if folder.is_dir() else []:
        ids.add(p.stem)
        data = mc.load_yaml(p, {})
        if isinstance(data, dict) and mc.norm(data.get("id")):
            ids.add(mc.norm(data["id"]))
    return ids


def check_catalog(root: Path, accounts: list[mc.Page]) -> Check:
    c = Check("catalog", "Products on account pages outside knowledge/products/", "0")
    ids = product_ids(root)
    used = [(p, f, str(v)) for p in accounts for f in ("recommended", "products_owned")
            for v in mc.as_list(p.meta.get(f))]
    if not used:
        return c.pending("no products on account pages yet")
    if not ids:
        return c.done(False, f"{len(used)} product refs, catalog empty",
                      ["knowledge/products/ is empty: fill it in the Phase 1 interview"])
    bad = [f"{p.rel}: {f} `{v}`" for p, f, v in used if v not in ids]
    return c.done(not bad, str(len(bad)), bad)


def check_suppression(root: Path) -> Check:
    c = Check("suppression", "Suppressed contact drafted", "0")
    sup = mc.read_csv(root / "wiki" / "suppression.csv")
    emails = {mc.norm(r.get("value")).lower(): mc.to_date(r.get("added_on")) for r in sup
              if mc.norm(r.get("type")).lower() == "email"}
    domains = {mc.norm(r.get("value")).lower().lstrip("@"): mc.to_date(r.get("added_on")) for r in sup
               if mc.norm(r.get("type")).lower() == "domain"}
    contact_email = {p.id: mc.norm(p.meta.get("email")).lower() for p in mc.iter_pages("contact", root)}
    account_domain = {p.id: mc.norm(p.meta.get("domain")).lower().removeprefix("www.")
                      for p in mc.iter_pages("account", root)}
    drafted = [t for t in mc.load_touches(root) if mc.norm(t.get("status")) == "drafted"]
    bad = []
    for t in drafted:
        when = mc.to_date(t.get("ts"))
        contact = mc.link_id(t.get("contact"), "contacts")
        email = contact.lower() if "@" in contact else contact_email.get(contact, "")
        hits = []
        if email in emails:
            hits.append((email, emails[email]))
        dom = email.split("@")[-1] if "@" in email else ""
        for d in {dom, account_domain.get(mc.link_id(t.get("account")), "")} - {""}:
            if d in domains:
                hits.append((d, domains[d]))
        for value, added in hits:
            if added is None or when is None or when >= added:
                bad.append(f"log/touches.csv {t.get('ts')} {t.get('account')}: draft to suppressed {value}")
    return c.done(not bad, f"{len(bad)} of {len(drafted)} drafts", bad)


def check_golden(root: Path) -> Check:
    c = Check("golden", "Golden accounts are well-formed", "all valid")
    folder = root / "evals" / "golden_accounts"
    tmpl = folder / "_template.md"
    problems = []
    if not tmpl.is_file():
        problems.append("evals/golden_accounts/_template.md is missing")
    files = sorted(p for p in folder.glob("*.md") if not p.name.startswith("_")) if folder.is_dir() else []
    for p in files:
        page = mc.read_page(p, root)
        rel = mc.rel_posix(p, root)
        if page is None or page.meta is None:
            problems.append(f"{rel}: no valid frontmatter")
            continue
        if mc.norm(page.meta.get("type")) != "account":
            problems.append(f"{rel}: type is not `account`")
        if mc.norm(page.meta.get("market")).upper() not in mc.MARKETS:
            problems.append(f"{rel}: market is not SG | MY | IN")
        if not re.search(r"^##\s+Expected\b", page.body, re.M):
            problems.append(f"{rel}: no `## Expected` section")
    if problems:
        return c.done(False, f"{len(files)} golden, {len(problems)} problem(s)", problems)
    return c.done(True, f"template ok, {len(files)} golden account(s) (10 per live market by Phase 3)")


def check_labelled(root: Path) -> Check:
    c = Check("labelled", "Labelled eval sets have the right columns", "all valid")
    bad = []
    rows = {}
    for name, want in LABELLED_HEADERS.items():
        p = root / "evals" / name
        if not p.is_file():
            bad.append(f"evals/{name} is missing")
            continue
        head = mc.read_text(p).splitlines()[:1]
        got = [h.strip() for h in head[0].lstrip("﻿").split(",")] if head else []
        extra = got[len(want):]
        if got[:len(want)] != want or any(x not in LABELLED_OPTIONAL.get(name, []) for x in extra):
            bad.append(f"evals/{name}: header {got} != {want} (+ optional {LABELLED_OPTIONAL.get(name, [])})")
        rows[name] = len(mc.read_csv(p))
    return c.done(not bad, ", ".join(f"{k} {v} rows" for k, v in rows.items()), bad)


# ----------------------------------------------------------------------------
# Phase 3: recommendation and entities
# ----------------------------------------------------------------------------
RECOMMENDATION_TARGET = 0.80


def golden_pages(root: Path) -> list[mc.Page]:
    folder = root / "evals" / "golden_accounts"
    files = sorted(p for p in folder.glob("*.md") if not p.name.startswith("_")) if folder.is_dir() else []
    pages = [mc.read_page(p, root) for p in files]
    return [p for p in pages if p is not None and p.meta]


def bullets(text: str) -> list[str]:
    return [re.sub(r"^[-*+]\s+", "", s.strip()).strip() for s in text.splitlines()
            if re.match(r"^\s*[-*+]\s+", s)]


def expected(golden: mc.Page) -> tuple[str, list[str], list[str]]:
    """(primary product or 'none', must-not products, must-not strings) from `## Expected`."""
    body = golden.body.split("## Expected", 1)[-1]
    rec = [b.split()[0].strip("`") for b in bullets(sub_section(body, "Recommendation")) if b.split()]
    primary = rec[0].lower() if rec else "none"
    products, strings = [], []
    for b in bullets(sub_section(body, "Must not")):
        m = re.match(r"^(?:product\s*:\s*)?`?([a-z0-9-]+)`?(?:\s|$)", b)
        s = re.match(r'^(?:text|name)\s*:\s*"?(.+?)"?\s*(?:—.*)?$', b, re.I)
        if s:
            strings.append(s.group(1).strip())
        elif m:
            products.append(m.group(1))
    return primary, products, strings


def sub_section(body: str, heading: str) -> str:
    m = re.search(rf"^###\s+{re.escape(heading)}\b.*?$(.*?)(?=^#{{2,3}}\s|\Z)", body, re.M | re.S | re.I)
    return mc.strip_comments(m.group(1)) if m else ""


def check_recommendation(root: Path) -> Check:
    c = Check("recommendation", "Recommendation matches golden expectation (10 accounts)", "≥ 80%")
    if not (root / "scripts" / "recommend.py").is_file():
        return c.pending("Phase 3: recommend.py missing")
    import recommend as rc
    import score as sc
    kn = sc.Knowledge(root)
    live = {str(m) for m in mc.as_list((mc.load_yaml(root / "knowledge" / "markets.yaml", {}) or {}).get("live"))}
    rows = []
    for g in golden_pages(root):
        gid = mc.norm(g.meta.get("id")) or g.path.stem
        if (live and mc.norm(g.meta.get("market")).upper() not in live) or \
                not (root / "wiki" / "accounts" / f"{gid}.md").is_file():
            continue
        rows.append((gid, g))
    if not rows:
        return c.pending("no golden account has a wiki page yet")
    good, details = 0, []
    for gid, g in rows:
        primary, never, _ = expected(g)
        r = rc.recommend(root, gid, kn)
        top = r["candidates"][0]["product"] if r.get("candidates") else "none"
        page = mc.read_page(root / "wiki" / "accounts" / f"{gid}.md", root)
        rec = [str(x) for x in mc.as_list(page.meta.get("recommended"))] if page and page.meta else []
        shown = rec[0] if rec else "none"
        bad_never = [p for p in rec if p in never]
        if top == primary and shown == primary and not bad_never:
            good += 1
        else:
            details.append(f"{gid}: expected {primary}, recommend.py {top}, page {shown}"
                           + (f", must-not {', '.join(bad_never)}" if bad_never else ""))
    pct = good / len(rows)
    return c.done(pct >= RECOMMENDATION_TARGET and len(rows) >= 1,
                  f"{good}/{len(rows)} ({100 * good // len(rows)}%)", details)


def check_entities(root: Path, accounts: list[mc.Page]) -> Check:
    c = Check("entities", "Fabricated entities on account pages (contacts, must-not names)", "0")
    contacts = {p.id: p for p in mc.iter_pages("contact", root)}
    must_not = {mc.norm(g.meta.get("id")) or g.path.stem: expected(g)[2] for g in golden_pages(root)}
    checked, bad = 0, []
    raw_cache: dict[str, str] = {}

    def raw_text(u: str) -> str:
        if u not in raw_cache:
            p = root / u
            raw_cache[u] = mc.read_text(p).lower() if p.is_file() else ""
        return raw_cache[u]

    for page in accounts:
        linked = re.findall(r"\[\[contacts/([^\]|#]+)", mc.section(page.body, "Contacts"))
        texts = [page.text]
        for cid in linked:
            checked += 1
            cp = contacts.get(cid.strip())
            if cp is None:
                bad.append(f"{page.rel}: contact [[contacts/{cid}]] has no page")
                continue
            texts.append(cp.text)
            name = mc.norm(cp.meta.get("name")).lower()
            sources = raw_links(cp.text) + raw_links(mc.norm(cp.meta.get("source"))) + raw_links(page.body)
            if not name or not any(name in raw_text(u) for u in sources):
                bad.append(f"{cp.rel}: name `{cp.meta.get('name')}` not found in any cited raw/ file")
        for s in must_not.get(page.id, []):
            checked += 1
            if any(s.lower() in t.lower() for t in texts):
                bad.append(f"{page.rel}: must-not text `{s}` appears")
    if checked == 0:
        return c.pending("no contacts or golden must-not names yet")
    return c.done(not bad, f"{len(bad)} of {checked} checked", bad)


# ----------------------------------------------------------------------------
# Pending checks (filled in by later phases)
# ----------------------------------------------------------------------------
def check_resolution(root: Path) -> Check:
    c = Check("resolution", "Entity resolution precision, auto-linked (50 labelled per market)", "≥ 95% each")
    if not (root / "scripts" / "resolve.py").is_file():
        return c.pending("Phase 2: resolve.py missing")
    import resolve
    rows = mc.read_csv(root / "evals" / "labeled_matches.csv")
    live = [str(m) for m in mc.as_list((mc.load_yaml(root / "knowledge" / "markets.yaml", {}) or {}).get("live"))]
    per = resolve.evaluate(root, rows)
    short = [f"{m} {per.get(m, {}).get('labelled', 0)}/{RESOLUTION_MIN_ROWS} labelled" for m in live
             if per.get(m, {}).get("labelled", 0) < RESOLUTION_MIN_ROWS]
    if short:
        return c.pending("Phase 2: " + ", ".join(short))
    parts, ok, details = [], True, []
    for m in live:
        st = per[m]
        if st["precision"] is None:
            ok = False
            parts.append(f"{m} no auto-links")
            continue
        ok = ok and st["precision"] >= RESOLUTION_TARGET
        parts.append(f"{m} {st['precision']:.1%} of {st['auto_linked']} auto-linked "
                     f"(recall {st['recall'] if st['recall'] is not None else 'n/a'})")
        details += [f"{m} wrong: {w}" for w in st["wrong"]]
    return c.done(ok, "; ".join(parts), details)


def saved_drafts(root: Path) -> list[mc.Page]:
    folder = root / "log" / "drafts"
    pages = [mc.read_page(p, root) for p in sorted(folder.glob("*.md"))] if folder.is_dir() else []
    return [p for p in pages if p and p.meta]


def draft_checks(root: Path) -> list[Check]:
    """send_window, language, draft_catalog, fabrication over log/drafts/ (saved by draft_check.py)."""
    import draft_check as dc
    checks = [Check("send_window", "Drafts outside the market's send window, holidays or channels", "0"),
              Check("language", "Non-English drafts without an approved pattern in that language", "0"),
              Check("draft_catalog", "Products or proof outside knowledge/ in drafts", "0"),
              Check("fabrication", "Names in drafts absent from the account page", "0")]
    drafts = saved_drafts(root)
    drafted = [t for t in mc.load_touches(root) if mc.norm(t.get("status")) == "drafted"]
    if not drafts and not drafted:
        return [c.pending("Phase 4: no drafts yet") for c in checks]
    reps = {r["id"]: r for r in mc.load_reps(root)}
    catalog = dc.load_products(root)
    bad: dict[str, list[str]] = {c.key: [] for c in checks}
    for d in drafts:
        m = d.meta
        market, rep = mc.norm(m.get("market")), reps.get(mc.norm(m.get("rep")))
        mcfg = dc.load_market(root, market)
        channel = mc.norm(m.get("channel"))
        if channel not in [mc.norm(c) for c in mc.as_list(mcfg.get("channels"))]:
            bad["send_window"].append(f"{d.rel}: channel {channel} not allowed in {market}")
        win = mc.norm(m.get("send_window"))
        if channel in ("email", "linkedin") and not dc.window_ok(mcfg, (rep or {}).get("send_window_override"), win):
            bad["send_window"].append(f"{d.rel}: send window `{win or '(none)'}` is not a {market} send day")
        lang = mc.norm(m.get("lang")) or "en"
        pat = dc.find_pattern(root, mc.norm(m.get("pattern"))) if m.get("pattern") else None
        pm = pat.meta if pat and pat.meta else {}
        if lang != "en" and not (mc.norm(pm.get("status")) == "approved" and mc.norm(pm.get("lang")) == lang):
            bad["language"].append(f"{d.rel}: lang {lang} without an approved {lang} pattern")
        for p in mc.as_list(m.get("products")):
            if str(p) not in catalog:
                bad["draft_catalog"].append(f"{d.rel}: product `{p}` not in knowledge/products/")
        acc_p = root / "wiki" / "accounts" / f"{m.get('account')}.md"
        con_p = root / "wiki" / "contacts" / f"{m.get('contact')}.md"
        account = mc.read_page(acc_p, root) if acc_p.is_file() else None
        contacts = [c for c in [mc.read_page(con_p, root) if con_p.is_file() else None] if c]
        if not account:
            bad["fabrication"].append(f"{d.rel}: account page missing")
            continue
        corpus = dc.source_corpus(root, account, contacts, rep)
        text = mc.norm(m.get("subject")) + "\n" + dc.strip_boilerplate(d.body, rep)
        bad["fabrication"] += [f"{d.rel}: {x}" for x in dc.entity_problems(text, corpus)]
    for t in drafted:
        for p in [x for x in mc.norm(t.get("products")).split(";") if x.strip()]:
            if p.strip() not in catalog:
                bad["draft_catalog"].append(f"log/touches.csv {t.get('ts')} {t.get('account')}: product `{p}`")
    n = len(drafts)
    for c in checks:
        c.done(not bad[c.key], f"{len(bad[c.key])} of {n} saved drafts", bad[c.key])
    return checks


def send_checks(root: Path) -> list[Check]:
    """ADR-0007: every send matches an approval and its preview, inside the window, not suppressed, with consent."""
    import datetime as dt_
    import json as json_
    import draft_check as dc
    checks = [Check("send_approval", "Sends without a matching approval and preview", "0"),
              Check("send_window_sent", "Sends outside the send window or on holidays", "0"),
              Check("send_suppressed", "Sends to suppressed contacts or domains", "0"),
              Check("send_consent", "WhatsApp sends without recorded opt-in", "0")]
    approvals = mc.read_csv(root / "log" / "approvals.csv")
    sent_rows = [a for a in approvals if mc.norm(a.get("decision")) == "sent"]
    script_touches = [t for t in mc.load_touches(root) if mc.norm(t.get("status")) == "sent"
                      and mc.norm(t.get("ref")).startswith(("gmail:", "wa:"))]
    if not sent_rows and not script_touches:
        return [c.pending("no sends yet (ADR-0007)") for c in checks]
    bad: dict[str, list[str]] = {c.key: [] for c in checks}
    by_ref = {mc.norm(a.get("ref")): a for a in sent_rows}
    reps = {r["id"]: r for r in mc.load_reps(root)}
    sup = mc.read_csv(root / "wiki" / "suppression.csv")
    for t in script_touches:
        a = by_ref.get(mc.norm(t.get("ref")))
        if not a:
            bad["send_approval"].append(f"touch {t.get('ts')} {t.get('account')} {t.get('ref')}: no approval row")
            continue
        prev = root / "log" / "outbox" / f"{a.get('preview')}.json"
        items = {}
        if prev.is_file():
            try:
                items = {str(i.get("n")): i for i in json_.loads(mc.read_text(prev)).get("items", [])}
            except ValueError:
                items = {}
        it = items.get(mc.norm(a.get("item")))
        if not it or it.get("body_sha256") != a.get("body_sha256"):
            bad["send_approval"].append(f"{t.get('ref')}: preview {a.get('preview')} item {a.get('item')} missing "
                                        "or its hash differs")
    for a in sent_rows:
        ref, ts = mc.norm(a.get("ref")), mc.norm(a.get("ts"))
        try:
            when = dt_.datetime.strptime(ts[:16], "%Y-%m-%d %H:%M")
        except ValueError:
            bad["send_window_sent"].append(f"{ref}: bad timestamp `{ts}`")
            continue
        acc = mc.read_page(root / "wiki" / "accounts" / f"{a.get('account')}.md", root)
        market = mc.norm((acc.meta if acc and acc.meta else {}).get("market"))
        mcfg = dc.load_market(root, market)
        days, start, end = dc.parse_window(mcfg, (reps.get(mc.norm(a.get("rep"))) or {}).get("send_window_override"))
        holidays = {d for d in (mc.to_date(h) for h in mc.as_list(mcfg.get("holidays"))) if d}
        if not (dc.is_send_day(when.date(), days, holidays) and start <= when.time() < end):
            bad["send_window_sent"].append(f"{ref}: {ts} is outside the {market or '?'} send window")
        con = mc.read_page(root / "wiki" / "contacts" / f"{a.get('contact')}.md", root)
        cmeta = (con.meta if con and con.meta else {}) or {}
        email = mc.norm(cmeta.get("email")).lower()
        for row in sup:
            value = mc.norm(row.get("value")).lower().lstrip("@")
            added = mc.to_date(row.get("added_on"))
            hit = value and (value == email or (email.endswith("@" + value)))
            if hit and (added is None or added <= when.date()):
                bad["send_suppressed"].append(f"{ref}: {email or a.get('to')} suppressed ({value}, {added})")
        if mc.norm(a.get("channel")) == "whatsapp":
            odate = mc.to_date(cmeta.get("whatsapp_opt_in_date"))
            src = mc.norm(cmeta.get("whatsapp_opt_in_source"))
            if not odate or odate > when.date() or not src.startswith("raw/") or not (root / src).is_file():
                bad["send_consent"].append(f"{ref}: {a.get('contact')} has no opt-in recorded before {when.date()}")
    n = len(sent_rows)
    for c in checks:
        c.done(not bad[c.key], f"{len(bad[c.key])} of {n} sends", bad[c.key])
    return checks


def check_replies(root: Path) -> Check:
    c = Check("replies", "Reply classification accuracy (≈40 labelled)", "≥ 90%")
    rows = mc.read_csv(root / "evals" / "labeled_replies.csv")
    if len(rows) < REPLIES_MIN_ROWS:
        return c.pending(f"Phase 4: {len(rows)} of {REPLIES_MIN_ROWS} labelled replies")
    import classify_reply as cr
    res = cr.evaluate(rows)
    details = [f"{w['id']}: {w['label']} -> {w['predicted']}: {w['text']}" for w in res["wrong"]]
    return c.done(res["accuracy"] >= REPLIES_TARGET,
                  f"{res['accuracy']:.1%} ({res['correct']}/{res['n']})", details)


def check_allocation(root: Path) -> Check:
    """Owned accounts and a fresh dry-run proposal against the hard constraints."""
    c = Check("allocation", "Allocation hard-constraint violations", "0")
    if not (root / "scripts" / "allocate.py").is_file():
        return c.pending("Phase 6: allocate.py missing")
    import argparse as ap_
    import allocate as al
    import claim as cl
    ctx = cl.Ctx(root)
    bad = []
    for a, p in ctx.accounts.items():
        o = mc.norm(p.meta.get("owner"))
        rep = ctx.reps.get(o)
        if not o or rep is None or not mc.is_active(p.meta):
            continue
        market = mc.norm(p.meta.get("market")).upper()
        if market not in [str(m).upper() for m in mc.as_list(rep.get("markets"))]:
            bad.append(f"{a}: owner {o} does not cover {market}")
        ok, why, _ = cl.territory_fit(p.meta, rep)
        if not ok:
            bad.append(f"{a}: {why}")
    for rid, rep in ctx.reps.items():
        cap = int(cl._num(rep.get("max_active")) or 0)
        if cap and ctx.active_count(rid) > cap:
            bad.append(f"{rid}: {ctx.active_count(rid)} active > max_active {cap}")
    opts = ap_.Namespace(tiers="A,B,C", exclude_rep=[], give=[], skip=[])
    P = al.propose(root, opts)
    for chk in P["checks"]:
        bad += [f"proposal: {chk['check']} broken by {v}" for v in chk["violations"]]
    owned = sum(1 for p in ctx.accounts.values() if mc.norm(p.meta.get("owner")))
    return c.done(not bad, f"{len(bad)} ({owned} owned accounts + dry-run proposal of {len(P['rows'])})", bad)


def pending_checks(root: Path) -> list[Check]:
    scripts = root / "scripts"
    weeks = 0
    dates = [mc.to_date(t.get("ts")) for t in mc.load_touches(root)]
    dates = [d for d in dates if d]
    if dates:
        weeks = (max(dates) - min(dates)).days // 7
    out = [
        Check("vam_bounds", "VAM writes outside allowed fields and sections", "0")
        .pending("Phase 5: VAM runs"),
        Check("calibration", "Tier A meeting rate vs tier C (after 4+ weeks)", "≥ 2×")
        .pending(f"needs 4+ weeks of touches (have {weeks})"),
        Check("draft_quality", "Draft quality (LLM-judge rubric)", "≥ 4/5")
        .pending("LLM-judge rubric runs in mama-weekly (Phase 7)"),
    ]
    return out


def run(root: Path) -> list[Check]:
    accounts = list(mc.iter_pages("account", root))
    live = [check_cited(root, accounts), check_catalog(root, accounts), check_suppression(root),
            check_golden(root), check_labelled(root), check_resolution(root)]
    live += [check_recommendation(root), check_entities(root, accounts)]
    live += draft_checks(root) + send_checks(root) + [check_replies(root), check_allocation(root)]
    return live + pending_checks(root)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the PLAN.md §16 evals over evals/, wiki/ and log/.")
    ap.add_argument("--json", action="store_true", help="print results as JSON")
    ap.add_argument("-v", "--verbose", action="store_true", help="list every failing item")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    checks = run(root)
    failed = [c for c in checks if c.status == "FAIL"]
    if args.json:
        print(json.dumps({"date": mc.today().isoformat(), "failed": len(failed),
                          "checks": [c.as_dict() for c in checks]}, indent=2))
        return 1 if failed else 0
    w = max(len(c.title) for c in checks)
    print(f"{'Check'.ljust(w)}  {'Target':10}  Result   Value")
    print(f"{'-' * w}  {'-' * 10}  -------  -----")
    for c in checks:
        print(f"{c.title.ljust(w)}  {c.target:10}  {c.status:7}  {c.value}")
        limit = None if args.verbose else 5
        for d in c.details[:limit] if c.status == "FAIL" else []:
            print(f"    - {d}")
        if c.status == "FAIL" and not args.verbose and len(c.details) > 5:
            print(f"    … {len(c.details) - 5} more (-v)")
    n = {s: sum(1 for c in checks if c.status == s) for s in ("PASS", "FAIL", "PENDING")}
    print(f"\neval: {n['PASS']} pass, {n['FAIL']} fail, {n['PENDING']} pending"
          + (" — FAILED" if failed else " — OK"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
