"""Is this Singapore company legitimate? Registry checks plus web evidence (/company-check, ADR-0008).

    python3 scripts/company_check.py check 202524169M [--json]
    python3 scripts/company_check.py check "Kestrel Physio" [--json]
    python3 scripts/company_check.py check 202524169M --evidence a.json --evidence b.json --save
    python3 scripts/company_check.py batch --owner me | --pool | --file uens.csv [--save]
    python3 scripts/company_check.py leads [--industries fnb,retail] [--limit 100] [--save]
    python3 scripts/company_check.py enrich-leads company-check/leads/<file>.csv vendor.json

Needs the local index: `python3 scripts/registry_data.py refresh`. Thresholds live in
knowledge/company_check.yaml. Each check returns pass, warn, fail, unknown or n/a, and the
verdict is one of: Not found, Not active, Red flag, Verified, Likely legitimate,
Registry OK - needs web check, Caution.

Evidence files come from the `verifier` subagents (one per focus: identity, people, risk):
    {"uen": "...", "website": {"url", "shows_name", "shows_uen", "snapshot"},
     "premises": {"seen", "detail", "snapshot"}, "employees": {"min", "max", "detail", "snapshot"},
     "activity": [{"date", "what", "snapshot"}], "adverse": [{"what", "snapshot"}], "mas_alert": false}
Vendor lookups (CompanyData, RocketReach, Apollo MCP) add {"vendor": [{"name", "employees", "industry",
"website", "founded", "snapshot"}]} and may set employees {"min", "max", "estimate": true, "source"}.
A vendor headcount is an estimate: it can pass E1 but never fails it on its own.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402
import registry_data as rd  # noqa: E402
from resolve import legal_form, name_tokens, norm_name  # noqa: E402

UEN_RE = mc.REG_PATTERNS["uen"][0]
RANK = {"pass": 0, "n/a": 0, "info": 0, "unknown": 1, "warn": 2, "fail": 3}
NO_AR = ("sole proprietorship", "partnership", "limited liability partnership", "limited partnership")


# ----------------------------------------------------------------------------
# Lookup
# ----------------------------------------------------------------------------
def connect(root: Path) -> sqlite3.Connection:
    p = rd.db_path(root)
    if not p.is_file():
        raise SystemExit("No registry index yet: run `python3 scripts/registry_data.py refresh` (about 1 GB, "
                         "a few minutes).")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def name_conf(query: str, name: str) -> float:
    q, n = name_tokens(query), name_tokens(name)
    if not q or not n:
        return 0.0
    if q == n:
        qf, nf = legal_form(query), legal_form(name)
        return 1.0 if not qf or qf == nf else 0.85
    qc, nc = "".join(q), "".join(n)
    if qc == nc:
        return 0.91
    seq = difflib.SequenceMatcher(None, qc, nc).ratio()
    conf = min(0.88, 0.9 * seq)
    if set(q) <= set(n) or set(n) <= set(q):
        conf = max(conf, 0.80 if len(set(q) & set(n)) >= 2 else conf)
    return round(conf, 3)


def lookup(con: sqlite3.Connection, query: str, cfg: dict) -> dict:
    """{'match': row|None, 'live': bool, 'candidates': [...], 'how': str}"""
    q = re.sub(r"\s+", "", query).upper()
    if UEN_RE.match(q):
        row = con.execute("SELECT * FROM live WHERE uen = ?", (q,)).fetchone()
        if row:
            return {"match": dict(row), "live": True, "candidates": [], "how": "UEN"}
        row = con.execute("SELECT * FROM all_entities WHERE uen = ?", (q,)).fetchone()
        return {"match": dict(row) if row else None, "live": False, "candidates": [], "how": "UEN"}
    nm = cfg.get("name_match") or {}
    auto, floor = float(nm.get("auto", 0.90)), float(nm.get("candidates", 0.70))
    nn = norm_name(query)
    toks = [t for t in re.findall(r"[a-z0-9]+", nn) if len(t) > 1]
    rows: dict[str, dict] = {}
    for r in con.execute("SELECT * FROM live WHERE name_norm = ?", (nn,)):
        rows[r["uen"]] = dict(r)
    if toks:
        fts = " AND ".join(f'"{t}"*' for t in toks[:6])
        for r in con.execute("SELECT l.* FROM names_fts f JOIN live l ON l.uen = f.uen WHERE names_fts MATCH ? "
                             "LIMIT 200", (fts,)):
            rows.setdefault(r["uen"], dict(r))
    scored = sorted(((name_conf(query, r["name"]), r) for r in rows.values()), key=lambda x: -x[0])
    cands = [{"uen": r["uen"], "name": r["name"], "conf": c, "status": r["status"]} for c, r in scored if c >= floor][:8]
    if scored and scored[0][0] >= auto and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.05):
        return {"match": scored[0][1], "live": True, "candidates": cands, "how": f"name ({scored[0][0]:.2f})"}
    if not cands:  # maybe it exists but isn't live
        r = con.execute("SELECT * FROM all_entities WHERE name_norm = ? LIMIT 1", (nn,)).fetchone()
        if r:
            return {"match": dict(r), "live": False, "candidates": [], "how": "name (not live)"}
    return {"match": None, "live": False, "candidates": cands, "how": "name"}


# ----------------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------------
def months_between(a: dt.date, b: dt.date) -> float:
    return (b - a).days / 30.44


def chk(cid: str, name: str, result: str, detail: str, source: str = "ACRA") -> dict:
    return {"id": cid, "check": name, "result": result, "detail": detail, "source": source}


def merge_evidence(paths: list[str]) -> dict:
    ev: dict = {"activity": [], "adverse": [], "vendor": []}
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        for item in data if isinstance(data, list) else [data]:
            for k, v in (item or {}).items():
                if k in ("activity", "adverse", "vendor"):
                    ev[k] += list(v or [])
                elif k == "mas_alert":
                    ev[k] = bool(ev.get(k)) or bool(v)
                elif isinstance(v, dict) and isinstance(ev.get(k), dict):
                    ev[k] = {**ev[k], **{a: b for a, b in v.items() if b not in (None, "")}}
                elif v not in (None, ""):
                    ev.setdefault(k, v)
    return ev


def crm_employees(root: Path, uen: str) -> tuple[int | None, str]:
    for page in mc.iter_pages("account", root):
        m = page.meta or {}
        if re.sub(r"\s+", "", mc.norm(m.get("reg_id"))).upper() == uen:
            try:
                return int(m.get("employees")), page.rel
            except (TypeError, ValueError):
                return None, page.rel
    return None, ""


def evaluate(root: Path, con: sqlite3.Connection, row: dict, cfg: dict, ev: dict | None) -> list[dict]:
    f = cfg.get("filters") or {}
    today = mc.today()
    out: list[dict] = []
    ev = ev or {}
    etype = (row.get("entity_type") or "").lower()

    # C1 annual return within N months (companies only)
    reg = mc.to_date(row.get("reg_date"))
    ar = mc.to_date(row.get("ar_date"))
    age = months_between(reg, today) if reg else None
    if any(x in etype for x in NO_AR):
        out.append(chk("C1", "Annual return", "n/a", f"{row.get('entity_type')}: no annual return"))
    elif age is not None and age < float(f.get("new_company_months", 19)) and not ar:
        out.append(chk("C1", "Annual return", "n/a", f"incorporated {reg} ({age:.0f} months): first annual return not due"))
    elif ar and months_between(ar, today) <= float(f.get("annual_return_months", 13)):
        out.append(chk("C1", "Annual return", "pass", f"filed {ar} ({months_between(ar, today):.0f} months ago)"))
    else:
        out.append(chk("C1", "Annual return", "fail",
                       f"last filed {ar or 'never'}; more than {f.get('annual_return_months', 13)} months"))

    # C2 accounts overdue
    due = mc.to_date(row.get("acct_due"))
    if due and (today - due).days > int(f.get("accounts_overdue_days", 30)) and not any(x in etype for x in NO_AR):
        out.append(chk("C2", "Accounts due", "warn", f"accounts were due {due}"))
    else:
        out.append(chk("C2", "Accounts due", "pass" if due else "n/a", f"next due {due}" if due else "none on record"))

    # C3 age
    if age is None:
        out.append(chk("C3", "Age", "unknown", "no registration date"))
    elif age < float(f.get("min_age_months", 12)):
        out.append(chk("C3", "Age", "warn", f"new company: registered {reg} ({age:.0f} months)"))
    else:
        out.append(chk("C3", "Age", "pass", f"registered {reg} ({age / 12:.1f} years)"))

    # P1-P3 address
    postal = row.get("postal") or ""
    has_addr = bool(postal and (row.get("street") or row.get("building")))
    out.append(chk("P1", "Address on record", "pass" if has_addr else "fail",
                   f"postal sector {postal[:2]}" if has_addr else "no local address in ACRA"))
    n_same = 0
    if postal:
        key = rd.address_key(postal, row.get("level"), row.get("unit"))
        r = con.execute("SELECT n FROM address_counts WHERE key = ?", (key,)).fetchone()
        n_same = int(r["n"]) if r else 0
    vo = postal in [str(x) for x in mc.as_list(f.get("virtual_office_postal_codes"))]
    if vo or n_same >= int(f.get("shared_address_strong", 100)):
        out.append(chk("P2", "Physical or virtual", "warn",
                       f"{n_same} live entities share this address" + (" (known virtual office)" if vo else "")
                       + ": corporate secretary or virtual office"))
    elif n_same >= int(f.get("shared_address_warn", 20)):
        out.append(chk("P2", "Physical or virtual", "warn", f"{n_same} live entities share this address: likely a "
                                                               "registered-address service"))
    else:
        out.append(chk("P2", "Physical or virtual", "pass" if has_addr else "unknown",
                       f"{n_same} live entit{'y' if n_same == 1 else 'ies'} at this address"))
    home = False
    if row.get("block") and row.get("street"):
        h = con.execute("SELECT residential, commercial FROM hdb WHERE key = ?",
                        (rd.norm_block(row["block"]) + "|" + rd.norm_street(row["street"]),)).fetchone()
        home = bool(h and h["residential"].startswith("Y") and not h["commercial"].startswith("Y"))
    out.append(chk("P3", "Home-based", "info" if home else "n/a",
                   "HDB residential block: home-based business" if home else "not an HDB residential block",
                   "HDB"))
    prem = ev.get("premises") or {}
    out.append(chk("P4", "Premises seen", "pass" if prem.get("seen") else ("unknown" if not prem else "warn"),
                   prem.get("detail") or ("no web evidence yet" if not prem else "no operating premises found"),
                   prem.get("snapshot") or "web"))

    # E1 employees > 3 (never guessed)
    need = int(f.get("min_employees", 4))
    emp = ev.get("employees") or {}
    crm_n, crm_src = crm_employees(root, row["uen"])
    lo = max([x for x in (emp.get("min"), crm_n) if isinstance(x, int)] or [0])
    hi = emp.get("max") if isinstance(emp.get("max"), int) else None
    est = " (vendor estimate)" if emp.get("estimate") and (emp.get("min") or 0) >= (crm_n or 0) else ""
    if lo >= need:
        src = emp.get("snapshot") if (emp.get("min") or 0) >= need else crm_src
        out.append(chk("E1", "Employees > 3", "pass", (emp.get("detail") or f"{lo} employees (CRM)") + est,
                       src or emp.get("source") or "web"))
    elif hi is not None and hi < need:
        # an estimate (profile-based counts undercount frontline staff) can warn, never fail
        out.append(chk("E1", "Employees > 3", "warn" if emp.get("estimate") else "fail",
                       (emp.get("detail") or f"at most {hi} people") + (" (vendor estimate)" if emp.get("estimate") else ""),
                       emp.get("snapshot") or emp.get("source") or "web"))
    else:
        out.append(chk("E1", "Employees > 3", "unknown", "no reliable headcount evidence (ACRA has none)", "web"))
    hints = []
    if (row.get("officers") or 0) >= 2:
        hints.append(f"{row['officers']} officers")
    if (row.get("auditors") or 0) > 0:
        hints.append("audited accounts")
    out.append(chk("E2", "Size hints", "info", ", ".join(hints) or "1 officer or none listed, no auditor"))

    # A1-A4 external
    b = con.execute("SELECT * FROM bca WHERE uen = ? ORDER BY expiry DESC LIMIT 1", (row["uen"],)).fetchone()
    if b and (mc.to_date(b["expiry"]) or today) >= today:
        out.append(chk("A1", "BCA contractor", "pass", f"{b['workhead']} grade {b['grade']}, valid to {b['expiry']}", "BCA"))
    else:
        out.append(chk("A1", "BCA contractor", "info" if b else "n/a",
                       f"registration expired {b['expiry']}" if b else "not a BCA registered contractor", "BCA"))
    since = (today - dt.timedelta(days=365 * int(f.get("gebiz_years", 3)))).isoformat()
    g = con.execute("SELECT COUNT(*) n, MAX(award_date) last, SUM(amount) total FROM gebiz WHERE name_norm = ? "
                    "AND award_date >= ?", (row.get("name_norm") or norm_name(row.get("name", "")), since)).fetchone()
    if g and g["n"]:
        out.append(chk("A2", "GeBIZ supplier", "pass", f"{g['n']} award(s), last {g['last']}, S${(g['total'] or 0):,.0f}", "GeBIZ"))
    else:
        out.append(chk("A2", "GeBIZ supplier", "n/a", f"no government award since {since}", "GeBIZ"))
    web = ev.get("website") or {}
    if web.get("url") and (web.get("shows_uen") or web.get("shows_name")):
        out.append(chk("A3", "Website identity", "pass",
                       f"{web['url']} shows the {'UEN' if web.get('shows_uen') else 'legal name'}", web.get("snapshot") or "web"))
    else:
        out.append(chk("A3", "Website identity", "unknown" if not web else "warn",
                       "no web evidence yet" if not web else f"{web.get('url') or 'no website'}: name/UEN not shown",
                       web.get("snapshot") or "web"))
    cutoff = (today - dt.timedelta(days=365)).isoformat()
    recent = [a for a in ev.get("activity") or [] if str(a.get("date", "")) >= cutoff]
    out.append(chk("A4", "Recent activity", "pass" if recent else ("unknown" if not ev else "warn"),
                   f"{len(recent)} item(s) in 12 months, e.g. {recent[0].get('what', '')}" if recent
                   else ("no web evidence yet" if not ev else "nothing found in 12 months"),
                   recent[0].get("snapshot", "web") if recent else "web"))

    # R1-R3 red flags
    adverse = ev.get("adverse") or []
    if adverse or ev.get("mas_alert"):
        out.append(chk("R1", "Adverse media / MAS alert", "fail",
                       "; ".join(a.get("what", "") for a in adverse) or "on the MAS Investor Alert List",
                       (adverse[0].get("snapshot") if adverse else "") or "web"))
    else:
        out.append(chk("R1", "Adverse media / MAS alert", "pass" if ev else "unknown",
                       "none found" if ev else "no web evidence yet", "web"))
    shell = any(str(row.get("ssic") or "").startswith(str(p)) for p in mc.as_list(f.get("shell_ssic_prefixes")))
    shared = any(c["id"] == "P2" and c["result"] == "warn" for c in out)
    no_web = not (web.get("url"))
    if shell and shared and (no_web or not ev):
        out.append(chk("R2", "Shell-like profile", "warn",
                       f"SSIC {row.get('ssic')} ({row.get('ssic_desc')}) at a shared address"
                       + (" with no website" if ev else "; check the web")))
    else:
        out.append(chk("R2", "Shell-like profile", "pass", "no"))
    fn = int(row.get("former_names") or 0)
    out.append(chk("R3", "Name changes", "warn" if fn >= int(f.get("name_changes_flag", 3)) else "pass",
                   f"{fn} former name(s)"))
    return out


def verdict(checks: list[dict], has_evidence: bool, cfg: dict) -> tuple[str, int, list[str]]:
    r = {c["id"]: c["result"] for c in checks}
    w = cfg.get("weights") or {}
    external = sum(1 for k in ("A1", "A2", "A3", "A4") if r.get(k) == "pass")
    score = (int(w.get("live", 25))
             + (int(w.get("annual_return", 20)) if r.get("C1") in ("pass", "n/a") else 0)
             + (int(w.get("physical_address", 15)) if r.get("P1") == "pass" and r.get("P2") != "warn" else 0)
             + (int(w.get("employees", 10)) if r.get("E1") == "pass" else 0)
             + min(int(w.get("external", 20)), 5 * external)
             + (int(w.get("age", 10)) if r.get("C3") == "pass" else 0))
    reasons = [f"{c['check']}: {c['detail']}" for c in checks if c["result"] in ("warn", "fail")]
    if r.get("R1") == "fail":
        return "Red flag", score, reasons
    ar_ok = r.get("C1") in ("pass", "n/a")
    physical = r.get("P1") == "pass" and r.get("P2") != "warn"
    if ar_ok and physical and r.get("E1") == "pass" and external >= 2 and r.get("R2") != "warn":
        return "Verified", score, reasons
    if not has_evidence:
        return ("Registry OK - needs web check" if ar_ok and physical and r.get("C2") != "warn" else "Caution"), \
            score, reasons
    if ar_ok and r.get("P1") == "pass" and external >= 1 and r.get("R2") != "warn":
        return "Likely legitimate", score, reasons
    return "Caution", score, reasons


def run_check(root: Path, con, cfg: dict, query: str, evidence: list[str] | None = None) -> dict:
    found = lookup(con, query, cfg)
    row = found["match"]
    base = {"query": query, "how": found["how"], "candidates": found["candidates"],
            "checked": mc.today().isoformat(), "dataset": _dataset(con)}
    if not row:
        return {**base, "verdict": "Not found" if not found["candidates"] else "Ambiguous", "score": 0,
                "checks": [chk("G1", "Found in ACRA", "fail" if not found["candidates"] else "unknown",
                               "no match" if not found["candidates"] else "several possible matches: pick one")]}
    if not found["live"]:
        return {**base, "uen": row["uen"], "name": row["name"], "status": row.get("status"), "verdict": "Not active",
                "score": 0, "checks": [chk("G1", "Found in ACRA", "pass", row["uen"]),
                                       chk("G2", "Live", "fail", f"status: {row.get('status') or 'unknown'}")]}
    ev = merge_evidence(evidence) if evidence else None
    checks = [chk("G1", "Found in ACRA", "pass", f"{row['uen']} by {found['how']}"),
              chk("G2", "Live", "pass", row["status"])] + evaluate(root, con, row, cfg, ev)
    v, score, reasons = verdict(checks, bool(ev), cfg)
    home = any(c["id"] == "P3" and c["result"] == "info" for c in checks)
    address = (f"Home-based (HDB residential), postal sector {row['postal'][:2]}" if home else
               " ".join(x for x in (row.get("block"), row.get("street"), f"#{row['level']}-{row['unit']}"
                                    if row.get("level") or row.get("unit") else "", row.get("building"),
                                    f"Singapore {row['postal']}" if row.get("postal") else "") if x))
    return {**base, "uen": row["uen"], "name": row["name"], "status": row["status"],
            "entity_type": row["entity_type"], "registered": row["reg_date"], "ssic": f"{row['ssic']} {row['ssic_desc']}",
            "address": address, "verdict": v, "score": score, "reasons": reasons, "checks": checks,
            "evidence": ev or {}}


def _dataset(con) -> str:
    m = dict(con.execute("SELECT key, value FROM meta").fetchall())
    return f"ACRA data updated {m.get('acra_updated') or '?'}, index built {m.get('built', '?')}"


# ----------------------------------------------------------------------------
# Reports
# ----------------------------------------------------------------------------
ICON = {"pass": "✅", "fail": "❌", "warn": "⚠️", "unknown": "❔", "n/a": "–", "info": "ℹ️"}


def report_md(res: dict, user: str) -> tuple[dict, str]:
    meta = {"type": "company_check", "uen": res.get("uen", ""), "name": res.get("name", ""),
            "verdict": res["verdict"], "score": res["score"], "checked": res["checked"], "by": user,
            "dataset": res["dataset"]}
    lines = [f"# {res.get('name') or res['query']} · {res['verdict']} ({res['score']}/100)", ""]
    if res.get("uen"):
        lines += [f"UEN {res['uen']} · {res.get('entity_type', '')} · {res.get('status', '')} · "
                  f"registered {res.get('registered', '')}", f"Address: {res.get('address', '')}",
                  f"Activity: {res.get('ssic', '')}", ""]
    lines += ["| Check | Result | Detail | Source |", "|---|---|---|---|"]
    for c in res["checks"]:
        src = c["source"]
        src = f"[{Path(src).name}]({src})" if "/" in src else src
        lines.append(f"| {c['id']} {c['check']} | {ICON.get(c['result'], '')} {c['result']} | "
                     f"{c['detail'].replace('|', '/')} | {src} |")
    vend = (res.get("evidence") or {}).get("vendor") or []
    if vend:
        lines += ["", "## Vendor data (estimates)", "| Vendor | Employees | Industry | Website | Founded |", "|---|---|---|---|---|"]
        for v in vend:
            lines.append(f"| {v.get('name', '')} | {v.get('employees', '')} | {v.get('industry', '')} | "
                         f"{v.get('website', '')} | {v.get('founded', '')} |")
    lines += ["", "## Sources", rd.LICENCE.format(what="ACRA, BCA, GeBIZ and HDB datasets", date=res["checked"]),
              "Web evidence is summarised in company-check/evidence/ (headline, URL, date, short summary)."]
    return meta, "\n".join(lines) + "\n"


def save(root: Path, res: dict, user: str) -> Path:
    folder = root / "company-check" / "reports"
    stem = f"{res['checked']}-{res.get('uen') or mc.slugify(res['query'])}"
    md = folder / f"{stem}.md"
    folder.mkdir(parents=True, exist_ok=True)
    mc.write_page(md, *report_md(res, user))
    mc.write_text(folder / f"{stem}.json", json.dumps(res, indent=2, ensure_ascii=False) + "\n")
    mc.append_log("check", user, f"company-check/{res.get('uen') or stem}", f"{res['verdict']} ({res['score']}/100)", root)
    return md


def batch_queries(root: Path, args) -> list[tuple[str, str]]:
    out = []
    if args.file:
        for r in mc.read_csv(Path(args.file)):
            q = mc.norm(r.get("uen") or r.get("UEN") or r.get("name") or r.get("company"))
            if q:
                out.append((q, q))
        return out
    user = mc.current_user(root) or {}
    for page in mc.iter_pages("account", root):
        m = page.meta or {}
        if mc.norm(m.get("market")) != "SG":
            continue
        owner = mc.norm(m.get("owner"))
        if (args.owner and owner != (user.get("id") if args.owner == "me" else args.owner)) or (args.pool and owner):
            continue
        q = re.sub(r"\s+", "", mc.norm(m.get("reg_id"))).upper() if mc.norm(m.get("reg_type")) == "uen" else ""
        out.append((page.id, q or mc.norm(m.get("name"))))
    return out


LEAD_FIELDS = ("name", "reg_id", "reg_type", "market", "industry", "city", "employees", "domain", "ssic",
               "ssic_desc", "registered", "annual_return", "officers", "rank", "why", "source")


def existing_keys(root: Path) -> tuple[set[str], set[str]]:
    uens, names = set(), set()
    for page in mc.iter_pages("account", root):
        m = page.meta or {}
        uens.add(re.sub(r"\s+", "", mc.norm(m.get("reg_id"))).upper())
        names.add(norm_name(mc.norm(m.get("name"))))
    return uens - {""}, names - {""}


def find_leads(root: Path, con, cfg: dict, industries: list[str], limit: int) -> list[dict]:
    """Live ACRA companies in the SG ICP industries that pass the registry rules (no vendor needed)."""
    f, lc = cfg.get("filters") or {}, cfg.get("leads") or {}
    fit = (mc.load_icp(root)["fit"].get("SG") or {})
    prefixes = fit.get("ssic_prefixes") or {}
    inds = industries or [str(i) for i in mc.as_list(fit.get("industries"))]
    pmap = {str(p): ind for ind in inds for p in mc.as_list(prefixes.get(ind))}
    if not pmap:
        raise SystemExit("no SSIC prefixes for those industries in knowledge/icp.md (SG ssic_prefixes)")
    today = mc.today()
    ar_cut = (today - dt.timedelta(days=int(30.44 * float(f.get("annual_return_months", 13))))).isoformat()
    age_cut = (today - dt.timedelta(days=int(30.44 * float(lc.get("min_age_months", 12))))).isoformat()
    types = [str(t) for t in mc.as_list(lc.get("entity_types"))] or ["Local Company"]
    shared = int(f.get("shared_address_warn", 20))
    shell = [str(x) for x in mc.as_list(f.get("shell_ssic_prefixes"))] if lc.get("exclude_shell", True) else []
    uens, names = existing_keys(root)
    where = " OR ".join("l.ssic LIKE ?" for _ in pmap)
    sql = (f"SELECT l.*, COALESCE(a.n, 0) AS same_addr FROM live l LEFT JOIN address_counts a ON a.key = "
           f"(l.postal || '|' || UPPER(LTRIM(l.level, '0')) || '|' || UPPER(LTRIM(l.unit, '0'))) "
           f"WHERE ({where}) AND l.entity_type IN ({','.join('?' * len(types))}) AND l.ar_date >= ? "
           f"AND l.reg_date <= ? AND l.postal != ''")
    rows = con.execute(sql, [p + "%" for p in pmap] + types + [ar_cut, age_cut]).fetchall()
    out = []
    for r in rows:
        r = dict(r)
        if r["uen"] in uens or r["name_norm"] in names or r["same_addr"] >= shared:
            continue
        if any(r["ssic"].startswith(x) for x in shell):
            continue
        if r.get("block") and r.get("street"):
            h = con.execute("SELECT residential, commercial FROM hdb WHERE key = ?",
                            (rd.norm_block(r["block"]) + "|" + rd.norm_street(r["street"]),)).fetchone()
            if h and h["residential"].startswith("Y") and not h["commercial"].startswith("Y"):
                continue  # home-based: not a fit and never listed (rule 8)
        ind = next(v for k, v in sorted(pmap.items(), key=lambda x: -len(x[0])) if r["ssic"].startswith(k))
        gebiz = con.execute("SELECT COUNT(*) FROM gebiz WHERE name_norm = ?", (r["name_norm"],)).fetchone()[0]
        bca = con.execute("SELECT COUNT(*) FROM bca WHERE uen = ?", (r["uen"],)).fetchone()[0]
        years = months_between(mc.to_date(r["reg_date"]), today) / 12
        rank = round(min(years, 10) * 2 + min(r["officers"] or 0, 5) * 3 + (5 if r["auditors"] else 0)
                     + (8 if gebiz else 0) + (5 if bca else 0), 1)
        why = [f"{years:.0f} yrs", f"AR {r['ar_date']}", f"{r['officers']} officers"]
        why += ["audited"] if r["auditors"] else []
        why += ["GeBIZ supplier"] if gebiz else []
        why += ["BCA contractor"] if bca else []
        out.append({"name": r["name"], "reg_id": r["uen"], "reg_type": "uen", "market": "SG", "industry": ind,
                    "city": "Singapore", "employees": "", "domain": "", "ssic": r["ssic"], "ssic_desc": r["ssic_desc"],
                    "registered": r["reg_date"], "annual_return": r["ar_date"], "officers": r["officers"],
                    "rank": rank, "why": "; ".join(why), "source": "acra-leads"})
    out.sort(key=lambda x: (-x["rank"], x["name"]))
    return out[:limit]


def write_leads(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[*LEAD_FIELDS, *[k for k in (rows[0] if rows else {}) if k not in LEAD_FIELDS]])
        w.writeheader()
        w.writerows(rows)


def band(value) -> tuple[int | None, int | None]:
    """'11-50' -> (11, 50); '200+' -> (200, None); 42 -> (42, 42)."""
    if isinstance(value, int):
        return value, value
    nums = [int(x) for x in re.findall(r"\d+", str(value or "").replace(",", ""))]
    if not nums:
        return None, None
    return (nums[0], None) if "+" in str(value) and len(nums) == 1 else (nums[0], nums[-1])


def enrich_leads(root: Path, csv_path: Path, vendor_json: Path) -> dict:
    """Merge vendor results {uen: {employees, domain, vendor}} into a leads CSV; flag the ICP size band."""
    data = json.loads(vendor_json.read_text(encoding="utf-8"))
    items = data if isinstance(data, dict) else {str(x.get("uen")): x for x in data}
    lo_icp, hi_icp = (mc.as_list((mc.load_icp(root)["fit"].get("SG") or {}).get("employees")) + [None, None])[:2]
    rows = mc.read_csv(csv_path)
    n = 0
    for r in rows:
        v = items.get(r.get("reg_id", ""))
        if not v:
            continue
        n += 1
        r["employees"] = str(v.get("employees", r.get("employees", "")))
        r["domain"] = v.get("domain") or r.get("domain", "")
        r["vendor"] = v.get("vendor", "")
        a, b = band(v.get("employees"))
        fits = a is not None and (hi_icp is None or a <= int(hi_icp)) and (b is None or lo_icp is None or b >= int(lo_icp))
        r["icp_size"] = "yes" if fits else ("unknown" if a is None else "no")
    write_leads(csv_path, rows)
    return {"rows": len(rows), "enriched": n, "in_band": sum(1 for r in rows if r.get("icp_size") == "yes")}


def print_result(res: dict) -> None:
    print(f"{res.get('name') or res['query']} · {res.get('uen', '')} · {res['verdict']} ({res['score']}/100)")
    if res.get("candidates") and not res.get("uen"):
        print("Possible matches:")
        for c in res["candidates"]:
            print(f"  {c['uen']}  {c['name']}  ({c['conf']:.2f})")
    for c in res["checks"]:
        print(f"  {ICON.get(c['result'], ' ')} {c['id']:3} {c['check']:26} {c['result']:8} {c['detail']}")
    print(f"  {res['dataset']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check whether a Singapore company is legitimate: ACRA, BCA, GeBIZ, "
                                             "HDB open data plus web evidence.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="one company by UEN or name")
    c.add_argument("query")
    c.add_argument("--evidence", action="append", default=[], help="verifier JSON (repeatable)")
    c.add_argument("--save", action="store_true", help="write company-check/reports/<date>-<uen>.md/.json")
    c.add_argument("--json", action="store_true")
    b = sub.add_parser("batch", help="registry checks for many companies")
    g = b.add_mutually_exclusive_group(required=True)
    g.add_argument("--owner", help="'me' or a rep id: that book's SG accounts")
    g.add_argument("--pool", action="store_true", help="unowned SG accounts")
    g.add_argument("--file", help="CSV with a uen or name column")
    b.add_argument("--save", action="store_true", help="write company-check/reports/batch-<date>.csv")
    b.add_argument("--json", action="store_true")
    ld = sub.add_parser("leads", help="live ACRA companies that fit the SG ICP and pass the registry rules")
    ld.add_argument("--industries", default="", help="ontology industries, comma-separated (default: icp.md SG)")
    ld.add_argument("--limit", type=int, default=0)
    ld.add_argument("--save", action="store_true", help="write company-check/leads/<date>-acra-leads.csv")
    ld.add_argument("--json", action="store_true")
    en = sub.add_parser("enrich-leads", help="merge vendor headcount/domain into a leads CSV")
    en.add_argument("csv")
    en.add_argument("vendor_json")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    cfg = rd.config(root)
    con = connect(root)
    user = (mc.current_user(root) or {}).get("id", "unknown")
    if args.cmd == "enrich-leads":
        print(json.dumps(enrich_leads(root, Path(args.csv), Path(args.vendor_json))))
        return 0
    if args.cmd == "leads":
        lim = args.limit or int((cfg.get("leads") or {}).get("default_limit", 100))
        rows = find_leads(root, con, cfg, [i.strip() for i in args.industries.split(",") if i.strip()], lim)
        if args.save:
            p = root / "company-check" / "leads" / f"{mc.today().isoformat()}-acra-leads.csv"
            write_leads(p, rows)
            mc.append_log("check", user, "company-check/leads", f"{len(rows)} ACRA leads", root)
            print(f"saved {mc.rel_posix(p, root)}")
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            for r in rows:
                print(f"{r['rank']:>5}  {r['reg_id']:12} {r['industry']:22} {r['name']}  ({r['why']})")
            print(f"{len(rows)} lead(s)")
        return 0
    if args.cmd == "check":
        res = run_check(root, con, cfg, args.query, args.evidence)
        if args.save and res.get("uen"):
            res["report"] = mc.rel_posix(save(root, res, user), root)
        print(json.dumps(res, indent=2, ensure_ascii=False)) if args.json else print_result(res)
        return 0 if res.get("uen") else 1
    rows = []
    for label, q in batch_queries(root, args):
        res = run_check(root, con, cfg, q)
        rows.append({"input": label, "uen": res.get("uen", ""), "name": res.get("name", ""),
                     "verdict": res["verdict"], "score": res["score"],
                     "issues": "; ".join(res.get("reasons", [])[:3])})
    if args.save:
        p = root / "company-check" / "reports" / f"batch-{mc.today().isoformat()}.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["input"])
            w.writeheader()
            w.writerows(rows)
        mc.append_log("check", user, "company-check/batch", f"{len(rows)} companies", root)
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        for r in rows:
            print(f"{r['verdict']:32} {r['score']:>3}  {r['uen']:12} {r['name'] or r['input']}  {r['issues']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
