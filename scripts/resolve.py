"""Entity resolution for mama-scan (Phase 2): the ONLY way signals link to accounts (AGENTS.md rule 10).

Input: a JSON list of scout / fetch_dataset items
    {market, source, source_type?, company_text, reg_id?, domain?, city?, industry?, ssic?,
     entity_type?, employees?, signal, url, date?, snapshot, evidence?|headline?, event?}

Matching, against accounts in the SAME market only:
    registry ID (or alt_ids) exact ................ 1.00
    website domain exact .......................... 0.95
    normalised name exact (+city agrees 0.95) ..... 0.92
    same name written without spaces .............. 0.91
    fuzzy name (never auto-links) ................. <= 0.88
Guards: a different valid registry ID on both sides caps at 0.50; a city
conflict costs 0.10; a domain conflict costs 0.10; a generic one-word name
caps at 0.85; two candidates within 0.05 of each other cap the best at 0.85.

Outcome per item (all written to log/signals.csv):
    >= 0.90 linked | 0.70–0.90 review (+ log/review.csv row) |
    < 0.70 new_lead if it fits the market's ICP (knowledge/icp.md), else dropped |
    rejected when the snapshot is not an existing raw/ file (rule 3).
Items whose signal is not an ontology term are dropped and logged `unmapped`
(rule 7); items already in log/signals.csv (same url or snapshot + company) are skipped.

--attach (mama-scan step 5, not in dry-run): re-reads each page, then adds the
cited Signals bullet and the `signals:` term to linked accounts, creates
new-lead pages (stage new, no owner) and event pages. Nothing else changes.

    python3 scripts/resolve.py raw/signals/2026-11-01/_run-2026-11-01-0200.json --run 2026-11-01-0200 --attach
    python3 scripts/resolve.py items.json --run test --dry-run --json
    python3 scripts/resolve.py --eval evals/labeled_matches.csv [--json]

Exit 0 on success, 1 on bad input or when the user is not the manager.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402

LINK_AT, REVIEW_AT = 0.90, 0.70
SIGNAL_FIELDS = ("ts", "source", "source_type", "url", "snapshot", "company_text", "account",
                 "match_conf", "signal", "status", "run")
REVIEW_FIELDS = ("ts", "signal_row", "company_text", "candidates", "decision", "decided_by", "decided_on")

# Name normalisation ----------------------------------------------------------
LEGAL = {"private", "limited", "pte", "pvt", "ltd", "sdn", "bhd", "berhad", "llp", "plc", "inc",
         "incorporated", "corporation", "corp", "company", "co", "opc", "llc", "lp"}
COUNTRY = {"s", "sg", "singapore", "m", "my", "malaysia", "india", "asia", "pacific", "apac", "sea"}
GENERIC = {"the", "and", "trading", "enterprise", "enterprises", "services", "service", "holdings",
           "holding", "group", "international", "global", "solutions", "management", "consultancy",
           "consulting", "partners", "industries", "ventures", "resources", "capital", "investments",
           "food", "foods", "retail", "logistics", "clinic", "clinics", "education", "learning",
           "centre", "center", "studio", "studios", "cafe", "restaurant", "kitchen", "store", "stores",
           "shop", "mart", "medical", "dental", "academy", "tech", "technologies", "technology",
           "design", "media", "network", "systems", "supply", "supplies", "express", "transport",
           "engineering", "construction", "marketing", "realty", "properties", "hub", "world", "one",
           "new", "best", "premier", "royal", "golden", "city", "lab", "labs"}
GENERIC_HOSTS = ("facebook.com", "instagram.com", "linkedin.com", "linktr.ee", "gmail.com", "yahoo.com",
                 "hotmail.com", "outlook.com", "wixsite.com", "business.site", "google.com", "tiktok.com",
                 "x.com", "twitter.com", "youtube.com", "shopee.sg", "lazada.sg", "grab.com")


def name_tokens(text: str) -> list[str]:
    t = unicodedata.normalize("NFKD", mc.norm(text)).encode("ascii", "ignore").decode("ascii").lower()
    t = t.replace("&", " and ").replace("@", " at ")
    t = re.sub(r"\((?:s|sg|singapore|m|malaysia|india|private|pte)\)", " ", t)
    toks = re.sub(r"[^a-z0-9]+", " ", t).split()
    while len(toks) > 1 and toks[-1] in LEGAL | COUNTRY:  # trailing legal form / country words
        toks.pop()
    if toks and toks[0] == "the" and len(toks) > 1:
        toks = toks[1:]
    return toks


def norm_name(text: str) -> str:
    return " ".join(name_tokens(text))


def distinctive(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in GENERIC and t not in COUNTRY and not t.isdigit()]


def is_generic(tokens: list[str]) -> bool:
    d = distinctive(tokens)
    return not d or (len(d) == 1 and len(d[0]) <= 4)


def norm_domain(value: str) -> str:
    d = mc.norm(value).lower()
    d = re.sub(r"^[a-z]+://", "", d).split("/")[0].split("?")[0].split(":")[0]
    d = d.removeprefix("www.")
    return "" if not d or any(d == h or d.endswith("." + h) for h in GENERIC_HOSTS) else d


# Legal-form families: an LLP and a Pte Ltd with the same name are different entities.
FORMS = {"llp": "llp", "lp": "lp", "pte": "private_co", "pvt": "private_co", "private": "private_co",
         "sdn": "private_co", "bhd": "private_co", "berhad": "public_co", "plc": "public_co"}


def legal_form(text: str) -> str:
    toks = re.sub(r"[^a-z0-9]+", " ", mc.norm(text).lower()).split()
    for t in reversed(toks[-3:]):
        if t in FORMS:
            return FORMS[t]
    return ""


def norm_reg(value: str) -> str:
    return re.sub(r"\s+", "", mc.norm(value)).upper()


# Knowledge -------------------------------------------------------------------
def id_types(root: Path) -> dict[str, list[str]]:
    data = mc.load_yaml(root / "knowledge" / "markets.yaml", {}) or {}
    out = {k: list(v) for k, v in mc.DEFAULT_ID_TYPES.items()}
    for m, cfg in (data.get("markets") or {}).items():
        if isinstance(cfg, dict) and cfg.get("id_types"):
            out[str(m)] = [str(x).lower() for x in mc.as_list(cfg["id_types"])]
    return out


def valid_reg(reg: str, market: str, types: dict) -> bool:
    return bool(reg) and any(mc.REG_PATTERNS[t][0].match(reg) for t in types.get(market, [])
                             if t in mc.REG_PATTERNS)


def reg_type(reg: str, market: str, types: dict) -> str:
    return next((t for t in types.get(market, []) if t in mc.REG_PATTERNS and mc.REG_PATTERNS[t][0].match(reg)), "")


def ontology(root: Path) -> dict:
    return mc.load_yaml(root / "knowledge" / "ontology.yaml", {}) or {}


# Accounts --------------------------------------------------------------------
class Account:
    __slots__ = ("id", "market", "name", "tokens", "compact", "regs", "domain", "city", "owner", "path",
                 "form", "source")

    def __init__(self, page: mc.Page, types: dict):
        m = page.meta or {}
        self.id, self.path = page.id, page.path
        self.market = mc.norm(m.get("market")).upper()
        self.name = mc.norm(m.get("name"))
        self.tokens = name_tokens(self.name)
        self.compact = "".join(self.tokens)
        regs = [m.get("reg_id")] + (list((m.get("alt_ids") or {}).values())
                                    if isinstance(m.get("alt_ids"), dict) else [])
        self.regs = {norm_reg(r) for r in regs if valid_reg(norm_reg(r), self.market, types)}
        self.domain = norm_domain(m.get("domain"))
        self.city = mc.norm(m.get("city")).lower()
        self.owner = mc.norm(m.get("owner"))
        self.form = legal_form(self.name)
        self.source = mc.norm(m.get("source"))


def load_accounts(root: Path, types: dict) -> list[Account]:
    return [Account(p, types) for p in mc.iter_pages("account", root)]


# Matching --------------------------------------------------------------------
def score_pair(item: dict, acc: Account, types: dict) -> tuple[float, str]:
    market = item["market"]
    reg = norm_reg(item.get("reg_id"))
    reg_ok = valid_reg(reg, market, types)
    if reg_ok and reg in acc.regs:
        return 1.0, "registry id"
    dom = norm_domain(item.get("domain"))
    toks = name_tokens(item.get("company_text"))
    name = " ".join(toks)
    compact = "".join(toks)
    city = mc.norm(item.get("city")).lower()
    conf, why = 0.0, ""
    if dom and acc.domain and dom == acc.domain:
        conf, why = 0.95, "domain"
    elif name and name == " ".join(acc.tokens):
        conf, why = (0.95, "name + city") if city and acc.city and city == acc.city else (0.92, "name")
    elif compact and compact == acc.compact and len(compact) >= 8:
        conf, why = 0.91, "name (spacing)"
    elif toks and acc.tokens:
        seq = difflib.SequenceMatcher(None, compact, acc.compact).ratio()
        a, b = set(distinctive(toks)), set(distinctive(acc.tokens))
        contain = (len(a & b) / min(len(a), len(b))) if a and b else 0.0
        conf = min(0.88, 0.9 * seq)
        if contain == 1.0:
            conf = max(conf, 0.80)
        elif contain == 0.0:
            conf = min(conf, 0.60)  # no shared distinctive word: never more than a weak hint
        why = f"fuzzy name ({seq:.2f})"
    if not why:
        return 0.0, ""
    if why != "domain":
        if is_generic(toks) or is_generic(acc.tokens):
            conf, why = min(conf, 0.85), why + ", generic name"
    form = legal_form(item.get("company_text"))
    if why != "domain" and form and acc.form and form != acc.form:
        conf, why = min(conf, 0.85), why + ", legal form differs"
    if reg_ok and acc.regs and reg not in acc.regs:
        conf, why = min(conf, 0.50), why + ", registry id differs"
    if dom and acc.domain and dom != acc.domain and why != "domain":
        conf, why = conf - 0.10, why + ", domain differs"
    if city and acc.city and city != acc.city:
        conf, why = conf - 0.10, why + ", city differs"
    return round(max(conf, 0.0), 3), why


def match(item: dict, accounts: list[Account], types: dict,
          skip_source: str = "") -> list[tuple[float, str, Account]]:
    market = mc.norm(item.get("market")).upper()
    item = {**item, "market": market}
    out = []
    for acc in accounts:
        if acc.market != market or (skip_source and acc.source == skip_source):
            continue
        conf, why = score_pair(item, acc, types)
        if conf > 0:
            out.append((conf, why, acc))
    out.sort(key=lambda x: -x[0])
    if len(out) > 1 and out[1][0] >= REVIEW_AT and out[0][0] - out[1][0] < 0.05 and out[0][0] < 1.0:
        best = out[0]
        out[0] = (min(best[0], 0.85), best[1] + ", ambiguous", best[2])
    return out


# ICP -------------------------------------------------------------------------
def icp_fit(item: dict, icp: dict, ssic_map: dict) -> tuple[bool, str]:
    fit = icp["fit"].get(item["market"]) or {}
    excl = icp.get("exclude") or {}
    text = mc.norm(item.get("company_text")).lower()
    for pat in mc.as_list(excl.get("name_patterns")):
        if re.search(str(pat), text, re.I):
            return False, f"excluded name pattern `{pat}`"
    et = mc.norm(item.get("entity_type")).lower()
    if et and any(str(x).lower() in et for x in mc.as_list(excl.get("entity_types"))):
        return False, f"excluded entity type `{item.get('entity_type')}`"
    emp = item.get("employees")
    try:
        emp = int(emp) if emp not in (None, "") else None
    except (TypeError, ValueError):
        emp = None
    if emp is not None and excl.get("max_employees") and emp > int(excl["max_employees"]):
        return False, "large enterprise"
    industry = mc.norm(item.get("industry"))
    if not industry and item.get("ssic"):
        for ind, pre in (ssic_map or {}).items():
            if any(str(item["ssic"]).startswith(str(p)) for p in mc.as_list(pre)):
                industry = str(ind)
    if not industry:
        return False, "industry unknown"
    if industry not in [str(x) for x in mc.as_list(fit.get("industries"))]:
        return False, f"industry `{industry}` not in ICP"
    band = mc.as_list(fit.get("employees"))
    if emp is not None and len(band) == 2 and not int(band[0]) <= emp <= int(band[1]):
        return False, f"{emp} employees outside {band[0]}–{band[1]}"
    regions = [str(r).lower() for r in mc.as_list(fit.get("regions"))]
    city = mc.norm(item.get("city")).lower()
    if regions and city and not any(r in city or city in r for r in regions):
        return False, f"region `{item.get('city')}` not in ICP"
    return True, industry


# Resolve ---------------------------------------------------------------------
def snapshot_ok(root: Path, snap: str) -> bool:
    s = mc.norm(snap)
    return s.startswith("raw/") and ".." not in s and (root / s).is_file()


def resolve_items(root: Path, items: list[dict], run: str) -> list[dict]:
    types = id_types(root)
    accounts = load_accounts(root, types)
    onto = ontology(root)
    terms = set((onto.get("signals") or {}).keys())
    icp = mc.load_icp(root)
    seen = {(r.get("url") or r.get("snapshot"), r.get("company_text"))
            for r in mc.read_csv(root / "log" / "signals.csv")}
    results = []
    for raw in items:
        if not isinstance(raw, dict) or raw.get("error") or raw.get("capped") or raw.get("suspicious"):
            continue
        item = {k: v for k, v in raw.items()}
        item["market"] = mc.norm(item.get("market")).upper()
        res = {"item": item, "account": "", "conf": 0.0, "status": "", "why": "", "candidates": []}
        results.append(res)
        if item.get("kind") == "event" or not mc.norm(item.get("company_text")):
            res["status"], res["why"] = "event" if item.get("kind") == "event" else "market_wide", "no company"
            continue
        key = (item.get("url") or item.get("snapshot"), item.get("company_text"))
        if key in seen:
            res["status"], res["why"] = "seen", "already in log/signals.csv"
            continue
        seen.add(key)
        if not snapshot_ok(root, item.get("snapshot")):
            res["status"], res["why"] = "rejected", "snapshot is not an existing raw/ file (rule 3)"
            continue
        if item["market"] not in mc.MARKETS:
            res["status"], res["why"] = "rejected", f"market `{item['market']}`"
            continue
        cands = match(item, accounts, types)
        res["candidates"] = [(a.id, c, w) for c, w, a in cands[:3]]
        best = cands[0] if cands else None
        if mc.norm(item.get("signal")) not in terms:
            res["status"], res["why"] = "dropped", "unmapped signal"
            res["unmapped"] = True
            if best:
                res["account"], res["conf"] = best[2].id, best[0]
            continue
        if best and best[0] >= LINK_AT:
            res.update(account=best[2].id, conf=best[0], status="linked", why=best[1])
        elif best and best[0] >= REVIEW_AT:
            res.update(account=best[2].id, conf=best[0], status="review", why=best[1])
        else:
            ok, why = icp_fit(item, icp, (icp["fit"].get(item["market"]) or {}).get("ssic_prefixes"))
            res.update(conf=best[0] if best else 0.0, status="new_lead" if ok else "dropped", why=why)
            if ok:
                item.setdefault("industry", why)
    return results


def write_logs(root: Path, results: list[dict], run: str, user: str) -> dict:
    sig_path = root / "log" / "signals.csv"
    n_rows = len(mc.read_csv(sig_path))
    ts = mc.now_stamp()
    counts: dict[str, int] = {}
    for r in results:
        st = r["status"]
        counts[st] = counts.get(st, 0) + 1
        if st in ("seen", "event", "market_wide"):
            continue
        it = r["item"]
        mc.append_csv(sig_path, {
            "ts": ts, "source": it.get("source", ""), "source_type": it.get("source_type", ""),
            "url": it.get("url", ""), "snapshot": it.get("snapshot", ""),
            "company_text": it.get("company_text", ""),
            "account": r["account"] if st in ("linked", "review") else "",
            "match_conf": f"{r['conf']:.2f}", "signal": it.get("signal", ""), "status": st, "run": run,
        }, SIGNAL_FIELDS)
        n_rows += 1
        r["signal_row"] = n_rows
        if st == "review":
            mc.append_csv(root / "log" / "review.csv", {
                "ts": ts, "signal_row": n_rows, "company_text": it.get("company_text", ""),
                "candidates": "; ".join(f"{a}:{c:.2f} ({w})" for a, c, w in r["candidates"]),
                "decision": "", "decided_by": "", "decided_on": ""}, REVIEW_FIELDS)
        if r.get("unmapped"):
            mc.append_log("unmapped", user, it.get("snapshot", ""),
                          f"signal `{it.get('signal', '')}` for {it.get('company_text', '')} is not an "
                          "ontology term", root)
    summary = ", ".join(f"{counts.get(k, 0)} {k}" for k in ("linked", "review", "new_lead", "dropped", "rejected"))
    mc.append_log("resolve", user, f"run {run}", f"{sum(counts.values())} items: {summary}", root)
    return counts


# Attach ----------------------------------------------------------------------
def add_to_section(body: str, heading: str, line: str) -> str:
    import ingest
    return ingest.add_to_section(body, heading, line)


def bullet(item: dict) -> str:
    evidence = mc.norm(item.get("evidence") or item.get("headline") or item.get("company_text"))
    evidence = " ".join(evidence.split()[:20])
    date = mc.norm(item.get("date")) or mc.today().isoformat()
    return f"- {item['signal']} — {evidence} ({date}) — [source]({item['snapshot']})"


def attach_signal(root: Path, path: Path, item: dict) -> bool:
    page = mc.read_page(path, root)  # re-read right before editing (rule 17)
    if page is None or page.meta is None:
        return False
    if item["snapshot"] in page.body and item["signal"] in mc.section(page.body, "Signals"):
        return False  # already attached
    signals = [str(s) for s in mc.as_list(page.meta.get("signals"))]
    changes = {"updated": mc.today()}
    if item["signal"] not in signals:
        changes["signals"] = signals + [item["signal"]]
    mc.update_frontmatter(path, changes)
    fresh = mc.read_page(path, root)
    mc.write_text(path, fresh.text[: len(fresh.text) - len(fresh.body)]
                  + add_to_section(fresh.body, "Signals", bullet(item)))
    return True


def create_lead(root: Path, item: dict, types: dict) -> str:
    import ingest
    idx = ingest.Index()
    for p in mc.iter_pages("account", root):
        idx.add(p.id, p.meta)
    reg = norm_reg(item.get("reg_id"))
    rec = {"market": item["market"], "name": mc.norm(item["company_text"]),
           "reg_id": reg if valid_reg(reg, item["market"], types) else "",
           "domain": norm_domain(item.get("domain")), "city": mc.norm(item.get("city")), "alt_ids": {}}
    hit = idx.find(rec)  # dedupe: registry ID -> domain -> name + city
    if hit:
        attach_signal(root, root / "wiki" / "accounts" / f"{hit[0]}.md", item)
        return hit[0]
    tmpl = mc.read_page(root / "templates" / "account.md", root)
    aid = mc.legal_slug(rec["name"], rec["market"], idx.ids)
    n, base = 2, aid
    while aid in idx.ids:
        aid, n = f"{base}-{n}", n + 1
    meta = {k: (v.copy() if isinstance(v, (list, dict)) else v) for k, v in tmpl.meta.items()}
    meta.update({"type": "account", "id": aid, "name": rec["name"], "market": rec["market"],
                 "source": item.get("source", ""), "stage": "new", "owner": None,
                 "signals": [item["signal"]], "updated": mc.today()})
    if rec["reg_id"]:
        meta.update(reg_id=rec["reg_id"], reg_type=reg_type(rec["reg_id"], rec["market"], types))
    for k in ("domain", "city"):
        if rec[k]:
            meta[k] = rec[k]
    if item.get("industry"):
        meta["industry"] = item["industry"]
    body = tmpl.body.replace("{name}", rec["name"])
    body = add_to_section(body, "Snapshot", f"- New lead from {item.get('source', '')} — "
                                            f"[source]({item['snapshot']}) ({mc.today().isoformat()})")
    body = add_to_section(body, "Signals", bullet(item))
    mc.write_page(root / "wiki" / "accounts" / f"{aid}.md", meta, body)
    return aid


def upsert_event(root: Path, ev: dict, market: str, source: str, account: str = "") -> str:
    name, year = mc.norm(ev.get("name")), mc.norm(ev.get("year"))
    if not name:
        return ""
    if not year:
        dates = [mc.to_date(d) for d in mc.as_list(ev.get("dates"))]
        year = str(dates[0].year) if dates and dates[0] else str(mc.today().year)
    eid = f"{mc.slugify(name)}-{year}"
    path = root / "wiki" / "events" / f"{eid}.md"
    if not path.is_file():
        tmpl = mc.read_page(root / "templates" / "event.md", root)
        meta = {k: (v.copy() if isinstance(v, (list, dict)) else v) for k, v in tmpl.meta.items()}
        meta.update({"type": "event", "id": eid, "name": name, "market": market,
                     "dates": [str(d) for d in mc.as_list(ev.get("dates"))], "venue": ev.get("venue"),
                     "url": ev.get("url"), "source": source,
                     "industries": [str(i) for i in mc.as_list(ev.get("industries"))],
                     "matched_accounts": [], "updated": mc.today()})
        body = tmpl.body.replace("{name}", name)
        if ev.get("snapshot"):
            body = add_to_section(body, "Why it matters", f"- Listed in [source]({ev['snapshot']})")
        mc.write_page(path, meta, body)
    if account:
        page = mc.read_page(path, root)
        matched = [str(a) for a in mc.as_list(page.meta.get("matched_accounts"))]
        if account not in matched:
            mc.update_frontmatter(path, {"matched_accounts": matched + [account], "updated": mc.today()})
            acc = mc.read_page(root / "wiki" / "accounts" / f"{account}.md", root)
            owner = mc.norm((acc.meta or {}).get("owner")) if acc else ""
            fresh = mc.read_page(path, root)
            line = f"- [[accounts/{account}]] — {owner or 'unowned'} — exhibiting; say hello at the stand"
            mc.write_text(path, fresh.text[: len(fresh.text) - len(fresh.body)]
                          + add_to_section(fresh.body, "Matched accounts", line))
    return eid


def attach(root: Path, results: list[dict]) -> dict:
    types = id_types(root)
    out = {"signals_attached": 0, "leads_created": [], "events": set()}
    for r in results:
        it, st = r["item"], r["status"]
        if st == "linked":
            if attach_signal(root, root / "wiki" / "accounts" / f"{r['account']}.md", it):
                out["signals_attached"] += 1
        elif st == "new_lead":
            r["account"] = create_lead(root, it, types)
            out["leads_created"].append(r["account"])
        if isinstance(it.get("event"), dict):
            acct = r["account"] if st in ("linked", "new_lead") else ""
            eid = upsert_event(root, {**it["event"], "snapshot": it.get("snapshot")}, it["market"],
                               it.get("source", ""), acct)
            if eid:
                out["events"].add(eid)
    out["events"] = sorted(out["events"])
    return out


# Eval ------------------------------------------------------------------------
def evaluate(root: Path, rows: list[dict]) -> dict:
    """Precision of auto-links on labelled rows (expected_account: id | new | reject)."""
    types = id_types(root)
    accounts = load_accounts(root, types)
    per: dict[str, dict] = {}
    for row in rows:
        m = mc.norm(row.get("market")).upper()
        st = per.setdefault(m, {"labelled": 0, "auto_linked": 0, "correct_links": 0, "review": 0,
                                "expected_links": 0, "wrong": [], "missed": []})
        st["labelled"] += 1
        exp = mc.norm(row.get("expected_account"))
        is_acct = exp not in ("", "new", "reject")
        st["expected_links"] += is_acct
        # A lead page created from this very source is the item itself, not a match:
        # compare against the accounts that existed before the scan.
        src = mc.norm(row.get("source"))
        cands = match({**row, "market": m}, accounts, types,
                      skip_source=src if src not in ("", "crm", "list", "synthetic") else "")
        best = cands[0] if cands else None
        if best and best[0] >= LINK_AT:
            st["auto_linked"] += 1
            if best[2].id == exp:
                st["correct_links"] += 1
            else:
                st["wrong"].append(f"{row.get('id')}: {row.get('company_text')} → {best[2].id} "
                                   f"({best[0]:.2f} {best[1]}), expected {exp}")
        elif best and best[0] >= REVIEW_AT:
            st["review"] += 1
        elif is_acct:
            st["missed"].append(f"{row.get('id')}: {row.get('company_text')} (expected {exp}; "
                                f"best {best[2].id + f' {best[0]:.2f}' if best else 'none'})")
    for st in per.values():
        st["precision"] = round(st["correct_links"] / st["auto_linked"], 3) if st["auto_linked"] else None
        st["recall"] = round(st["correct_links"] / st["expected_links"], 3) if st["expected_links"] else None
    return per


# Main ------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Resolve scanned items to accounts (the only linker, rule 10).")
    ap.add_argument("items", nargs="?", help="JSON list of items (scout / fetch_dataset output)")
    ap.add_argument("--run", help="run id <YYYY-MM-DD>-<HHMM>")
    ap.add_argument("--attach", action="store_true", help="also attach signals, create new-lead and event pages")
    ap.add_argument("--dry-run", action="store_true", help="resolve and print; write nothing")
    ap.add_argument("--eval", metavar="CSV", help="score precision on a labelled CSV (writes nothing)")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    if args.eval:
        per = evaluate(root, mc.read_csv(Path(args.eval) if Path(args.eval).is_absolute() else root / args.eval))
        if args.json:
            print(json.dumps(per, indent=2))
        else:
            for m, st in sorted(per.items()):
                p = "n/a" if st["precision"] is None else f"{st['precision']:.1%}"
                r = "n/a" if st["recall"] is None else f"{st['recall']:.1%}"
                print(f"{m}: {st['labelled']} labelled · auto-linked {st['auto_linked']} · precision {p} · "
                      f"recall {r} · review {st['review']}")
                for w in st["wrong"]:
                    print(f"  WRONG  {w}")
                for w in st["missed"]:
                    print(f"  missed {w}")
        return 0
    if not args.items or not args.run:
        ap.error("items file and --run are required (or --eval)")
    user = mc.current_user(root)
    if not args.dry_run and (not user or mc.norm(user.get("role")) != "manager"):
        print("Refused: resolve.py writes run as the manager or the runner (manager identity).")
        return 1
    path = Path(args.items)
    path = path if path.is_absolute() else root / path
    try:
        items = json.loads(mc.read_text(path))
        assert isinstance(items, list)
    except Exception as exc:  # noqa: BLE001
        print(f"Cannot read items from {args.items}: {exc}".splitlines()[0])
        return 1
    results = resolve_items(root, items, args.run)
    counts: dict = {}
    attached: dict = {}
    if not args.dry_run:
        counts = write_logs(root, results, args.run, user["id"])
        if args.attach:
            attached = attach(root, results)
    else:
        for r in results:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
    if args.json:
        print(json.dumps({"run": args.run, "dry_run": args.dry_run, "counts": counts, "attached": attached,
                          "results": [{"company_text": r["item"].get("company_text", ""),
                                       "source": r["item"].get("source", ""), "url": r["item"].get("url", ""),
                                       "signal": r["item"].get("signal", ""),
                                       "status": r["status"], "account": r["account"],
                                       "conf": r["conf"], "why": r["why"], "snapshot": r["item"].get("snapshot", ""),
                                       "candidates": r["candidates"]} for r in results]},
                         indent=2, default=str))
    else:
        print(f"{'DRY RUN — ' if args.dry_run else ''}run {args.run}: " +
              ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
        for r in results:
            print(f"  {r['status']:9} {r['conf']:.2f}  {r['item'].get('company_text', '')[:50]:50} "
                  f"→ {r['account'] or '-'}  ({r['why']})")
        if attached:
            print(f"attached {attached['signals_attached']} signal(s); new leads: "
                  f"{', '.join(attached['leads_created']) or 'none'}; events: {', '.join(attached['events']) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
