"""Company insights: statistics, charts and summaries on the registry index (generative UI for chat).

    python3 scripts/company_analytics.py company 197200078R          # one company: profile, checks, peers, evidence
    python3 scripts/company_analytics.py segment --industry clinics  # or --ssic 86 / --district 52 / --name kopi
    python3 scripts/company_analytics.py book --owner me             # or --pool / --file leads.csv
    python3 scripts/company_analytics.py compare 197200078R 199701833R 201900002D
  add --cards (mama-card blocks for the console), --json (the spec) or --html <path> (a shareable page).

Every number is computed here from company-check/data/registry.sqlite (ACRA, BCA, GeBIZ, HDB open data,
as of the ACRA data date), saved reports and evidence. The model only explains; it never invents figures.
Card types: stats, chart, table, company, compare (console/cards.schema.json, docs/UI.md).
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import company_check as cc  # noqa: E402
import mama_common as mc  # noqa: E402
import registry_data as rd  # noqa: E402

GROUPS = (("Registry", ("G", "C")), ("Address", ("P",)), ("People", ("E",)), ("Outside signals", ("A",)),
          ("Red flags", ("R",)))
AGE_BANDS = ((0, 1, "< 1 yr"), (1, 3, "1–3 yrs"), (3, 5, "3–5 yrs"), (5, 10, "5–10 yrs"), (10, 20, "10–20 yrs"),
             (20, 999, "20+ yrs"))
NO_AR = cc.NO_AR


# ----------------------------------------------------------------------------
# Data helpers
# ----------------------------------------------------------------------------
class Ctx:
    def __init__(self, root: Path):
        self.root = root
        self.cfg = rd.config(root)
        self.con = cc.connect(root)
        meta = dict(self.con.execute("SELECT key, value FROM meta").fetchall())
        self.as_of = mc.to_date(str(meta.get("acra_updated") or "")[:10]) or mc.today()
        self.f = self.cfg.get("filters") or {}
        self._hdb = None
        self._gebiz = None
        self._bca = None

    @property
    def hdb(self) -> set[str]:
        if self._hdb is None:
            self._hdb = {r[0] for r in self.con.execute(
                "SELECT key FROM hdb WHERE residential LIKE 'Y%' AND commercial NOT LIKE 'Y%'")}
        return self._hdb

    @property
    def gebiz(self) -> set[str]:
        if self._gebiz is None:
            since = (self.as_of - dt.timedelta(days=365 * int(self.f.get("gebiz_years", 3)))).isoformat()
            self._gebiz = {r[0] for r in self.con.execute("SELECT DISTINCT name_norm FROM gebiz WHERE award_date >= ?",
                                                         (since,))}
        return self._gebiz

    @property
    def bca(self) -> set[str]:
        if self._bca is None:
            self._bca = {r[0] for r in self.con.execute("SELECT DISTINCT uen FROM bca WHERE expiry >= ?",
                                                       (self.as_of.isoformat(),))}
        return self._bca

    def licence(self) -> str:
        return rd.LICENCE.format(what="ACRA, BCA, GeBIZ and HDB datasets", date=self.as_of.isoformat())


def rows_where(ctx: Ctx, where: str, params: list) -> list[dict]:
    sql = ("SELECT l.*, COALESCE(a.n, 0) AS same_addr FROM live l LEFT JOIN address_counts a ON a.key = "
           "(l.postal || '|' || UPPER(LTRIM(l.level, '0')) || '|' || UPPER(LTRIM(l.unit, '0'))) WHERE " + where)
    return [dict(r) for r in ctx.con.execute(sql, params)]


def age_years(ctx: Ctx, r: dict) -> float | None:
    d = mc.to_date(r.get("reg_date"))
    return (ctx.as_of - d).days / 365.25 if d else None


def files_on_time(ctx: Ctx, r: dict) -> bool | None:
    """True/False for companies that file annual returns; None when not applicable (sole props, new)."""
    if any(x in (r.get("entity_type") or "").lower() for x in NO_AR):
        return None
    age = age_years(ctx, r)
    if age is not None and age * 12 < float(ctx.f.get("new_company_months", 19)):
        return None
    ar = mc.to_date(r.get("ar_date"))
    return bool(ar and (ctx.as_of - ar).days / 30.44 <= float(ctx.f.get("annual_return_months", 13)))


def is_home(ctx: Ctx, r: dict) -> bool:
    return bool(r.get("block") and r.get("street")) and \
        (rd.norm_block(r["block"]) + "|" + rd.norm_street(r["street"])) in ctx.hdb


def pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def metrics(ctx: Ctx, rows: list[dict]) -> dict:
    ages = [a for a in (age_years(ctx, r) for r in rows) if a is not None]
    filing = [x for x in (files_on_time(ctx, r) for r in rows) if x is not None]
    shared = int(ctx.f.get("shared_address_warn", 20))
    return {"count": len(rows),
            "median_age": round(statistics.median(ages), 1) if ages else None,
            "on_time_pct": pct(sum(filing), len(filing)), "filers": len(filing),
            "shared_pct": pct(sum(1 for r in rows if r["same_addr"] >= shared), len(rows)),
            "home_pct": pct(sum(1 for r in rows if is_home(ctx, r)), len(rows)),
            "gebiz": sum(1 for r in rows if r["name_norm"] in ctx.gebiz),
            "bca": sum(1 for r in rows if r["uen"] in ctx.bca),
            "median_officers": statistics.median([r["officers"] or 0 for r in rows]) if rows else None}


def tone(value: float, good: float, warn: float, higher_is_good: bool = True) -> str:
    if higher_is_good:
        return "good" if value >= good else ("warn" if value >= warn else "risk")
    return "good" if value <= good else ("warn" if value <= warn else "risk")


# ----------------------------------------------------------------------------
# Card builders
# ----------------------------------------------------------------------------
def card(ctype: str, title: str, refs: list[str] | None = None, **fields) -> dict:
    return {"type": ctype, "title": title, "agent": "mama", **fields, "refs": refs or ["company-check/README.md"]}


def stats_card(ctx: Ctx, title: str, m: dict, subtitle: str = "") -> dict:
    tiles = [{"label": "Live companies", "value": m["count"], "tone": "neutral"},
             {"label": "Median age", "value": m["median_age"], "unit": "yrs", "tone": "neutral"},
             {"label": "Filing on time", "value": m["on_time_pct"], "unit": "%",
              "note": f"of {m['filers']:,} that file annual returns", "tone": tone(m["on_time_pct"], 85, 70)},
             {"label": "Shared / virtual address", "value": m["shared_pct"], "unit": "%",
              "tone": tone(m["shared_pct"], 10, 25, higher_is_good=False)},
             {"label": "Home-based (HDB)", "value": m["home_pct"], "unit": "%", "tone": "neutral"},
             {"label": "GeBIZ suppliers", "value": m["gebiz"], "note": "award in 3 yrs", "tone": "good" if m["gebiz"] else "neutral"},
             {"label": "BCA contractors", "value": m["bca"], "tone": "good" if m["bca"] else "neutral"}]
    return card("stats", title, subtitle=subtitle or f"ACRA data as of {ctx.as_of}", tiles=tiles)


def by_year_chart(ctx: Ctx, rows: list[dict], title: str) -> dict:
    years = list(range(ctx.as_of.year - 9, ctx.as_of.year + 1))
    counts = {y: 0 for y in years}
    for r in rows:
        d = mc.to_date(r.get("reg_date"))
        if d and d.year in counts:
            counts[d.year] += 1
    return card("chart", title, kind="bar", unit="companies", series=[{"label": str(y), "value": counts[y]} for y in years],
                note=f"still live today, by year registered ({ctx.as_of.year} is year to date)")


def age_chart(ctx: Ctx, rows: list[dict]) -> dict:
    counts = [0] * len(AGE_BANDS)
    for r in rows:
        a = age_years(ctx, r)
        if a is None:
            continue
        for i, (lo, hi, _) in enumerate(AGE_BANDS):
            if lo <= a < hi:
                counts[i] += 1
                break
    return card("chart", "How old are they?", kind="bar", unit="companies",
                series=[{"label": b[2], "value": c} for b, c in zip(AGE_BANDS, counts)])


def mix_chart(rows: list[dict], key: str, title: str, top: int = 6, kind: str = "donut") -> dict:
    counts: dict[str, int] = {}
    for r in rows:
        k = r.get(key) or "(blank)"
        counts[k] = counts.get(k, 0) + 1
    items = sorted(counts.items(), key=lambda x: -x[1])
    series = [{"label": k, "value": v} for k, v in items[:top]]
    if len(items) > top:
        series.append({"label": "Other", "value": sum(v for _, v in items[top:])})
    return card("chart", title, kind=kind, unit="companies", series=series)


def ssic_chart(rows: list[dict], top: int = 8) -> dict:
    """Group by SSIC code (descriptions are often blank or vary); label with the most common description."""
    counts: dict[str, int] = {}
    descs: dict[str, dict[str, int]] = {}
    for r in rows:
        code = r.get("ssic") or "?"
        counts[code] = counts.get(code, 0) + 1
        if r.get("ssic_desc"):
            d = descs.setdefault(code, {})
            d[r["ssic_desc"]] = d.get(r["ssic_desc"], 0) + 1
    items = sorted(counts.items(), key=lambda x: -x[1])
    def name(code: str) -> str:
        d = descs.get(code)
        return f"{code} {max(d, key=d.get).title()}" if d else f"SSIC {code}"
    series = [{"label": name(k)[:60], "value": v} for k, v in items[:top]]
    if len(items) > top:
        series.append({"label": "Other", "value": sum(v for _, v in items[top:])})
    return card("chart", "Top activities (primary SSIC)", kind="hbar", unit="companies", series=series)


def district_chart(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for r in rows:
        p = r.get("postal") or ""
        if len(p) >= 2:
            counts[p[:2]] = counts.get(p[:2], 0) + 1
    items = sorted(counts.items(), key=lambda x: -x[1])[:10]
    return card("chart", "Where they are (postal sector)", kind="hbar", unit="companies",
                series=[{"label": f"Sector {k}", "value": v} for k, v in items],
                note="first two digits of the registered postal code")


# ----------------------------------------------------------------------------
# Questions
# ----------------------------------------------------------------------------
def latest_report(root: Path, uen: str) -> dict | None:
    files = sorted((root / "company-check" / "reports").glob(f"*-{uen}.json"))
    if not files:
        return None
    try:
        return json.loads(mc.read_text(files[-1])) | {"report_file": mc.rel_posix(files[-1].with_suffix(".md"), root)}
    except ValueError:
        return None


def evidence_list(root: Path, uen: str) -> list[dict]:
    out = []
    for p in sorted((root / "company-check" / "evidence" / uen).glob("*.md")) if uen else []:
        text = mc.read_text(p)
        head = re.search(r"^#\s+(.+)$", text, re.M)
        date = re.search(r"^- Date:\s*(.+)$", text, re.M)
        sup = re.search(r"^- Supports:\s*(.+)$", text, re.M)
        out.append({"date": (date.group(1) if date else "")[:20], "headline": (head.group(1) if head else p.stem)[:90],
                    "supports": (sup.group(1) if sup else "")[:40], "file": mc.rel_posix(p, root)})
    return out


def company_card(res: dict) -> dict:
    by = {c["id"]: c for c in res.get("checks", [])}
    groups = []
    for name, prefixes in GROUPS:
        checks = [{"id": c["id"], "check": c["check"], "result": c["result"], "detail": c["detail"][:160]}
                  for cid, c in by.items() if cid[0] in prefixes]
        if checks:
            groups.append({"name": name, "checks": checks})
    vend = (res.get("evidence") or {}).get("vendor") or []
    facts = {"Entity type": res.get("entity_type", ""), "Registered": res.get("registered", ""),
             "Activity": res.get("ssic", ""), "Address": res.get("address", "")}
    if vend:
        facts["Vendor headcount"] = f"{vend[0].get('employees', '')} ({vend[0].get('name', '')}, estimate)"
    refs = [x for x in [res.get("report_file"), "company-check/README.md"] if x]
    return card("company", res.get("name") or res.get("query", ""), refs=refs, uen=res.get("uen", ""),
                status=res.get("status", ""), verdict=res["verdict"], score=res["score"], facts=facts, groups=groups,
                subtitle=res.get("dataset", ""))


def q_company(ctx: Ctx, query: str) -> dict:
    found = cc.lookup(ctx.con, query, ctx.cfg)
    uen = (found.get("match") or {}).get("uen", "")
    saved = latest_report(ctx.root, uen) if uen else None
    res = saved or cc.run_check(ctx.root, ctx.con, ctx.cfg, query)
    if not res.get("uen") or res["verdict"] in ("Not found", "Ambiguous", "Not active"):
        cards = [company_card(res)] if res.get("uen") else []
        if res.get("candidates"):
            cards.append(card("table", "Possible matches", columns=[{"key": "uen", "label": "UEN"},
                                                                     {"key": "name", "label": "Name"},
                                                                     {"key": "conf", "label": "Match", "align": "right"}],
                              rows=res["candidates"][:10]))
        return {"title": res.get("name") or query, "summary": [f"{res['verdict']}"], "cards": cards}
    row = dict(ctx.con.execute("SELECT * FROM live WHERE uen = ?", (res["uen"],)).fetchone())
    peers = rows_where(ctx, "l.ssic = ?", [row["ssic"]])
    m = metrics(ctx, peers)
    cards = [company_card(res),
             stats_card(ctx, f"Peers: SSIC {row['ssic']} {row['ssic_desc'] or ''}".strip()[:120], m,
                        subtitle=f"{m['count']:,} live companies with the same primary activity, as of {ctx.as_of}")]
    age = age_years(ctx, row) or 0
    cards.append(card("chart", "This company vs its peers", kind="hbar", unit="",
                      series=[{"label": "Age (yrs) · this company", "value": round(age, 1)},
                              {"label": "Age (yrs) · peer median", "value": m["median_age"] or 0},
                              {"label": "Officers · this company", "value": row["officers"] or 0},
                              {"label": "Officers · peer median", "value": m["median_officers"] or 0}]))
    ev = evidence_list(ctx.root, res["uen"])
    if ev:
        cards.append(card("table", "Web evidence", refs=[e["file"] for e in ev[:6]],
                          columns=[{"key": "date", "label": "Date"}, {"key": "headline", "label": "What"},
                                   {"key": "supports", "label": "Supports"}], rows=ev[:12]))
    c1 = next((c for c in res.get("checks", []) if c["id"] == "C1"), {})
    summary = [f"{res['name']} ({res['uen']}): {res['verdict']}, {res['score']}/100.",
               f"{round(age, 1)} years old vs a peer median of {m['median_age']} among {m['count']:,} live peers.",
               f"Annual return: {c1.get('result', '?')}: {c1.get('detail', '')}."]
    return {"title": res["name"], "summary": summary, "cards": cards}


def segment_filter(ctx: Ctx, args) -> tuple[str, list, str]:
    where, params, label = ["1=1"], [], []
    if args.industry:
        fit = mc.load_icp(ctx.root)["fit"].get("SG") or {}
        pre = [str(p) for p in mc.as_list((fit.get("ssic_prefixes") or {}).get(args.industry))]
        if not pre:
            raise SystemExit(f"no SSIC prefixes for industry `{args.industry}` in knowledge/icp.md")
        where.append("(" + " OR ".join("l.ssic LIKE ?" for _ in pre) + ")")
        params += [p + "%" for p in pre]
        label.append(args.industry.replace("_", " "))
    if args.ssic:
        where.append("l.ssic LIKE ?")
        params.append(args.ssic + "%")
        label.append(f"SSIC {args.ssic}*")
    if args.district:
        where.append("l.postal LIKE ?")
        params.append(args.district[:2] + "%")
        label.append(f"postal sector {args.district[:2]}")
    if args.name:
        where.append("l.name_norm LIKE ?")
        params.append("%" + cc.norm_name(args.name) + "%")
        label.append(f"name contains “{args.name}”")
    if args.type:
        where.append("l.entity_type = ?")
        params.append(args.type)
        label.append(args.type)
    return " AND ".join(where), params, ", ".join(label) or "all live companies"


def q_segment(ctx: Ctx, args) -> dict:
    where, params, label = segment_filter(ctx, args)
    rows = rows_where(ctx, where, params)
    if not rows:
        return {"title": label, "summary": [f"No live companies match {label}."], "cards": []}
    m = metrics(ctx, rows)
    title = f"Singapore {label}".strip()
    cards = [stats_card(ctx, title[:120], m), by_year_chart(ctx, rows, "New companies per year"), age_chart(ctx, rows),
             mix_chart(rows, "entity_type", "Entity types"), district_chart(rows),
             ssic_chart(rows)]
    if args.industry:
        leads = cc.find_leads(ctx.root, ctx.con, ctx.cfg, [args.industry], 15)
        if leads:
            cards.append(card("table", "Best new leads in this segment", columns=[
                {"key": "name", "label": "Company"}, {"key": "reg_id", "label": "UEN"},
                {"key": "why", "label": "Why"}, {"key": "rank", "label": "Rank", "align": "right"}],
                rows=[{k: x[k] for k in ("name", "reg_id", "why", "rank")} for x in leads],
                actions=[{"label": "Save these leads", "prompt": f"/company-check leads --industries {args.industry}",
                          "style": "primary"}]))
    summary = [f"{m['count']:,} live companies ({label}), median age {m['median_age']} years.",
               f"{m['on_time_pct']}% file their annual return on time; {m['shared_pct']}% use a shared or virtual "
               f"address; {m['home_pct']}% are home-based.",
               f"{m['gebiz']:,} won a government contract in 3 years; {m['bca']:,} are BCA contractors."]
    return {"title": title, "summary": summary, "cards": cards}


def q_book(ctx: Ctx, args) -> dict:
    results = []
    for label, q in cc.batch_queries(ctx.root, args):
        found = cc.lookup(ctx.con, q, ctx.cfg)
        uen = (found.get("match") or {}).get("uen", "")
        res = (latest_report(ctx.root, uen) if uen else None) or cc.run_check(ctx.root, ctx.con, ctx.cfg, q)
        results.append((label, res))
    if not results:
        return {"title": "Book", "summary": ["No SG accounts to check."], "cards": []}
    order = ["Verified", "Likely legitimate", "Registry OK - needs web check", "Caution", "Red flag", "Not active",
             "Not found", "Ambiguous"]
    mix = {v: sum(1 for _, r in results if r["verdict"] == v) for v in order}
    ok = mix["Verified"] + mix["Likely legitimate"] + mix["Registry OK - needs web check"]
    scores = [r["score"] for _, r in results if r.get("uen")]
    tiles = [{"label": "Companies checked", "value": len(results), "tone": "neutral"},
             {"label": "Clean registry", "value": pct(ok, len(results)), "unit": "%", "tone": tone(pct(ok, len(results)), 80, 60)},
             {"label": "Caution / red flag", "value": mix["Caution"] + mix["Red flag"],
              "tone": "risk" if mix["Caution"] + mix["Red flag"] else "good"},
             {"label": "Not active / not found", "value": mix["Not active"] + mix["Not found"],
              "tone": "risk" if mix["Not active"] + mix["Not found"] else "good"},
             {"label": "Average score", "value": round(statistics.mean(scores)) if scores else 0, "unit": "/100", "tone": "neutral"}]
    who = "My book" if args.owner == "me" else ("Pool" if args.pool else (args.file or args.owner or "Companies"))
    cards = [card("stats", f"{who}: company checks", subtitle=f"ACRA data as of {ctx.as_of}", tiles=tiles),
             card("chart", "Verdicts", kind="donut", unit="companies",
                  series=[{"label": k, "value": v} for k, v in mix.items() if v])]
    issues = [{"company": r.get("name") or label, "verdict": r["verdict"],
               "issue": "; ".join(r.get("reasons", [])[:2])[:140] or r.get("status", "")}
              for label, r in results if r["verdict"] in ("Caution", "Red flag", "Not active", "Not found", "Ambiguous")]
    if issues:
        cards.append(card("table", "Needs attention", columns=[{"key": "company", "label": "Company"},
                                                               {"key": "verdict", "label": "Verdict"},
                                                               {"key": "issue", "label": "Why"}], rows=issues[:25]))
    best = sorted([(r["score"], r) for _, r in results if r["verdict"] in order[:3]], key=lambda x: -x[0])[:10]
    if best:
        cards.append(card("table", "Cleanest to work first", columns=[{"key": "company", "label": "Company"},
                                                                      {"key": "verdict", "label": "Verdict"},
                                                                      {"key": "score", "label": "Score", "align": "right"}],
                          rows=[{"company": r["name"], "verdict": r["verdict"], "score": s} for s, r in best]))
    summary = [f"{len(results)} companies: {ok} clean on the registry, {mix['Caution'] + mix['Red flag']} need a look, "
               f"{mix['Not active'] + mix['Not found']} not active or not found."]
    return {"title": f"{who}: company checks", "summary": summary, "cards": cards}


def q_compare(ctx: Ctx, queries: list[str]) -> dict:
    res = []
    for q in queries[:5]:
        found = cc.lookup(ctx.con, q, ctx.cfg)
        uen = (found.get("match") or {}).get("uen", "")
        res.append((latest_report(ctx.root, uen) if uen else None) or cc.run_check(ctx.root, ctx.con, ctx.cfg, q))
    ids = [c for c in ("C1", "C3", "P2", "P3", "E1", "A1", "A2", "A3", "A4", "R1", "R2")]
    names = {"C1": "Annual return", "C3": "Age", "P2": "Physical or virtual", "P3": "Home-based", "E1": "Employees > 3",
             "A1": "BCA contractor", "A2": "GeBIZ supplier", "A3": "Website identity", "A4": "Recent activity",
             "R1": "Adverse media", "R2": "Shell-like"}
    rows = [{"check": "Status", "values": [{"result": "pass" if r.get("status", "").startswith("Live") else "fail",
                                            "text": r.get("status", r["verdict"])} for r in res]}]
    for cid in ids:
        vals = []
        for r in res:
            c = next((x for x in r.get("checks", []) if x["id"] == cid), None)
            vals.append({"result": c["result"], "text": c["detail"][:70]} if c else {"result": "n/a", "text": ""})
        rows.append({"check": names[cid], "values": vals})
    comp = card("compare", "Side by side", refs=[r["report_file"] for r in res if r.get("report_file")] or None,
                companies=[{"uen": r.get("uen", ""), "name": r.get("name") or r.get("query", ""), "verdict": r["verdict"],
                            "score": r["score"]} for r in res], rows=rows)
    best = max(res, key=lambda r: r["score"])
    return {"title": "Compare: " + " · ".join((r.get("name") or r.get("query", ""))[:30] for r in res),
            "summary": [f"Highest score: {best.get('name') or best.get('query')} ({best['verdict']}, {best['score']}/100)."],
            "cards": [comp]}


# ----------------------------------------------------------------------------
# Output: cards, markdown, HTML
# ----------------------------------------------------------------------------
def to_cards(spec: dict) -> str:
    out = [" ".join(spec["summary"])]
    for c in spec["cards"]:
        out.append("```mama-card\n" + json.dumps(c, ensure_ascii=False) + "\n```")
    return "\n\n".join(out)


def to_text(spec: dict) -> str:
    lines = [f"# {spec['title']}", *spec["summary"], ""]
    for c in spec["cards"]:
        lines.append(f"## {c['title']}")
        if c["type"] == "stats":
            lines += [f"- {t['label']}: {t['value']}{t.get('unit', '')}" + (f" ({t['note']})" if t.get("note") else "")
                      for t in c["tiles"]]
        elif c["type"] == "chart":
            top = max([s["value"] for s in c["series"]] or [1]) or 1
            lines += [f"  {s['label'][:28]:28} {'█' * max(1, round(24 * s['value'] / top)) if s['value'] else ''} {s['value']}"
                      for s in c["series"]]
        elif c["type"] == "table":
            cols = c["columns"]
            lines.append("| " + " | ".join(x["label"] for x in cols) + " |")
            lines.append("|" + "---|" * len(cols))
            lines += ["| " + " | ".join(str(r.get(x["key"], "")) for x in cols) + " |" for r in c["rows"]]
        elif c["type"] == "company":
            lines.append(f"{c['verdict']} · {c['score']}/100 · {c['status']}")
            for g in c["groups"]:
                lines.append(f"- {g['name']}: " + "; ".join(f"{x['id']} {x['result']}" for x in g["checks"]))
        elif c["type"] == "compare":
            lines.append("| Check | " + " | ".join(x["name"][:24] for x in c["companies"]) + " |")
            lines.append("|" + "---|" * (len(c["companies"]) + 1))
            lines.append("| Verdict | " + " | ".join(f"{x['verdict']} ({x['score']})" for x in c["companies"]) + " |")
            lines += ["| " + r["check"] + " | " + " | ".join(v["result"] for v in r["values"]) + " |" for r in c["rows"]]
        lines.append("")
    return "\n".join(lines)


TONE = {"good": "#15803D", "warn": "#B45309", "risk": "#B91C1C", "neutral": "var(--ink)"}
RES = {"pass": "#15803D", "fail": "#B91C1C", "warn": "#B45309", "unknown": "#8A84A3", "n/a": "#A49DBA", "info": "#1D4ED8"}
PALETTE = ["#6D28D9", "#0F766E", "#1D4ED8", "#C2410C", "#BE185D", "#15803D", "#A16207", "#5B5670"]


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def html_chart(c: dict) -> str:
    s = c.get("series") or []
    top = max([x["value"] for x in s] or [1]) or 1
    if c["kind"] == "donut":
        total = sum(x["value"] for x in s) or 1
        acc, arcs, legend = 0.0, [], []
        for i, x in enumerate(s):
            frac = x["value"] / total
            arcs.append(f'<circle r="40" cx="60" cy="60" fill="none" stroke="{PALETTE[i % 8]}" stroke-width="18" '
                        f'stroke-dasharray="{frac * 251.3:.2f} 251.3" stroke-dashoffset="{-acc * 251.3:.2f}" '
                        f'transform="rotate(-90 60 60)"><title>{_e(x["label"])}: {x["value"]}</title></circle>')
            legend.append(f'<li><i style="background:{PALETTE[i % 8]}"></i>{_e(x["label"])}<b>{x["value"]:,}</b>'
                          f'<small>{100 * frac:.0f}%</small></li>')
            acc += frac
        return f'<div class="donut"><svg viewBox="0 0 120 120" role="img" aria-label="{_e(c["title"])}">{"".join(arcs)}' \
               f'</svg><ul>{"".join(legend)}</ul></div>'
    if c["kind"] == "hbar":
        return '<div class="hbars">' + "".join(
            f'<div class="hb"><span>{_e(x["label"])}</span><div><i style="width:{100 * x["value"] / top:.1f}%"></i></div>'
            f'<b>{x["value"]:,}</b></div>' for x in s) + "</div>"
    bars = "".join(f'<div class="vb"><b>{x["value"]:,}</b><i style="height:{100 * x["value"] / top:.1f}%"></i>'
                   f'<span>{_e(x["label"])}</span></div>' for x in s)
    return f'<div class="vbars">{bars}</div>'


def html_card(c: dict) -> str:
    head = f'<h3>{_e(c["title"])}</h3>' + (f'<p class="sub">{_e(c.get("subtitle", ""))}</p>' if c.get("subtitle") else "")
    t = c["type"]
    if t == "stats":
        def val(x):
            v = x["value"]
            return f"{v:,}" if isinstance(v, int) else _e(v if v is not None else "–")
        body = '<div class="tiles">' + "".join(
            f'<div class="tile"><span>{_e(x["label"])}</span><b style="color:{TONE.get(x.get("tone", "neutral"))}">'
            f'{val(x)}{_e(x.get("unit", ""))}</b>' + (f'<small>{_e(x["note"])}</small>' if x.get("note") else "")
            + "</div>" for x in c["tiles"]) + "</div>"
    elif t == "chart":
        body = html_chart(c) + (f'<p class="note">{_e(c["note"])}</p>' if c.get("note") else "")
    elif t == "table":
        cols = c["columns"]
        body = "<div class='tw'><table><thead><tr>" + "".join(f"<th>{_e(x['label'])}</th>" for x in cols) + \
               "</tr></thead><tbody>" + "".join("<tr>" + "".join(
                   f"<td class='{x.get('align', '')}'>{_e(r.get(x['key'], ''))}</td>" for x in cols) + "</tr>"
                   for r in c["rows"]) + "</tbody></table></div>"
    elif t == "company":
        facts = "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in c["facts"].items() if v)
        groups = "".join(f"<h4>{_e(g['name'])}</h4>" + "".join(
            f'<div class="chk"><i style="background:{RES.get(x["result"], "#999")}"></i><b>{_e(x["id"])}</b>'
            f'<span>{_e(x["check"])}</span><em style="color:{RES.get(x["result"], "#999")}">{_e(x["result"])}</em>'
            f'<small>{_e(x["detail"])}</small></div>' for x in g["checks"]) for g in c["groups"])
        body = f'<div class="verdict"><b>{_e(c["verdict"])}</b><span>{c["score"]}/100</span><small>UEN {_e(c["uen"])} · ' \
               f'{_e(c["status"])}</small></div><dl>{facts}</dl>{groups}'
    elif t == "compare":
        hdr = "".join(f"<th>{_e(x['name'])}<br><small>{_e(x['verdict'])} · {x['score']}/100</small></th>" for x in c["companies"])
        rows = "".join("<tr><td>" + _e(r["check"]) + "</td>" + "".join(
            f'<td><i style="background:{RES.get(v["result"], "#999")}"></i>{_e(v["text"] or v["result"])}</td>'
            for v in r["values"]) + "</tr>" for r in c["rows"])
        body = f"<div class='tw'><table class='cmp'><thead><tr><th></th>{hdr}</tr></thead><tbody>{rows}</tbody></table></div>"
    else:
        body = f"<pre>{_e(json.dumps(c, indent=2))}</pre>"
    return f'<section class="card c-{t}">{head}{body}</section>'


def to_html(spec: dict, licence: str) -> str:
    cards = "".join(html_card(c) for c in spec["cards"])
    summary = "".join(f"<li>{_e(s)}</li>" for s in spec["summary"])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(spec['title'])} · Sales Mama insights</title>
<style>
:root{{--ground:#F6F4FF;--surface:#fff;--ink:#16131F;--muted:#5B5670;--line:#E4DFF5;--mama:#6D28D9;--lime:#C8F031;color-scheme:light}}
@media (prefers-color-scheme:dark){{:root{{--ground:#0F0D16;--surface:#1D1928;--ink:#F4F2FA;--muted:#A9A3BE;--line:#342E46;color-scheme:dark}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--ground);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;padding:28px 16px}}
main{{max-width:1080px;margin:0 auto;display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(min(100%,480px),1fr))}}
header{{max-width:1080px;margin:0 auto 18px}}h1{{font-size:30px;margin:0 0 6px;letter-spacing:-.5px}}header ul{{margin:0;padding-left:18px;color:var(--muted)}}
.brand{{display:inline-flex;gap:8px;align-items:center;font-weight:700;margin-bottom:10px}}.brand i{{background:var(--ink);color:var(--lime);font-style:normal;border-radius:8px;padding:3px 7px;font-size:12px}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:18px 20px;overflow:hidden}}.c-company,.c-compare,.c-stats{{grid-column:1/-1}}
h3{{margin:0;font-size:17px}}.sub,.note{{color:var(--muted);font-size:13px;margin:2px 0 10px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-top:10px}}.tile{{border:1px solid var(--line);border-radius:14px;padding:10px 12px}}.tile span{{display:block;color:var(--muted);font-size:12.5px}}.tile b{{font-size:24px;display:block}}.tile small{{color:var(--muted);font-size:11.5px}}
.vbars{{display:flex;align-items:flex-end;gap:6px;height:180px;margin-top:10px}}.vb{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;gap:4px;font-size:11px}}.vb i{{width:100%;background:var(--mama);border-radius:6px 6px 2px 2px;min-height:2px}}.vb span{{color:var(--muted)}}
.hbars{{display:grid;gap:7px;margin-top:10px}}.hb{{display:grid;grid-template-columns:minmax(120px,40%) 1fr auto;gap:10px;align-items:center;font-size:13px}}.hb span{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.hb div{{background:var(--line);border-radius:99px;height:10px}}.hb i{{display:block;height:100%;background:var(--mama);border-radius:99px}}
.donut{{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-top:6px}}.donut svg{{width:150px;height:150px}}.donut ul{{list-style:none;padding:0;margin:0;font-size:13px;flex:1;min-width:180px}}.donut li{{display:flex;gap:8px;align-items:center;padding:2px 0}}.donut li i{{width:10px;height:10px;border-radius:3px}}.donut li b{{margin-left:auto}}.donut li small{{color:var(--muted);width:36px;text-align:right}}
.tw{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}}th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}}th{{color:var(--muted);font-weight:600}}td.right{{text-align:right}}
.cmp td i,.chk i{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}}
.verdict{{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;margin:10px 0}}.verdict b{{background:var(--lime);color:#16131F;padding:4px 10px;border-radius:10px;font-size:18px}}.verdict small{{color:var(--muted)}}
dl{{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;font-size:13.5px;margin:6px 0 4px}}dt{{color:var(--muted)}}dd{{margin:0}}
h4{{margin:12px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:1px;color:var(--muted)}}.chk{{display:grid;grid-template-columns:14px 34px minmax(150px,200px) 64px 1fr;gap:6px;font-size:13px;align-items:baseline}}.chk em{{font-style:normal;font-weight:600}}.chk small{{color:var(--muted)}}
footer{{max-width:1080px;margin:18px auto 0;color:var(--muted);font-size:12px}}
@media (max-width:600px){{.chk{{grid-template-columns:14px 34px 1fr 60px}}.chk small{{grid-column:2/-1}}}}
</style></head><body>
<header><div class="brand"><i>SM</i>Sales Mama · company insights</div><h1>{_e(spec['title'])}</h1><ul>{summary}</ul></header>
<main>{cards}</main>
<footer>{_e(licence)} Results are indicative, not legal or credit advice. Generated {mc.now_stamp()}.</footer>
</body></html>"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Company insights: statistics, charts and summaries on the registry index.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("company", help="one company: profile, checks, peers, evidence")
    c.add_argument("query")
    s = sub.add_parser("segment", help="a slice of live companies")
    s.add_argument("--industry", help="ICP industry (knowledge/icp.md), e.g. clinics")
    s.add_argument("--ssic", help="SSIC code prefix, e.g. 86")
    s.add_argument("--district", help="postal sector, e.g. 52")
    s.add_argument("--name", help="name contains")
    s.add_argument("--type", help="exact entity type, e.g. 'Local Company'")
    b = sub.add_parser("book", help="verdict mix for a book, the pool or a CSV")
    g = b.add_mutually_exclusive_group(required=True)
    g.add_argument("--owner")
    g.add_argument("--pool", action="store_true")
    g.add_argument("--file")
    cp = sub.add_parser("compare", help="2–5 companies side by side")
    cp.add_argument("queries", nargs="+")
    for p in (c, s, b, cp):
        p.add_argument("--cards", action="store_true", help="print mama-card blocks (console)")
        p.add_argument("--json", action="store_true", help="print the report spec")
        p.add_argument("--html", help="write a shareable HTML page to this path")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    ctx = Ctx(mc.repo_root())
    if args.cmd == "company":
        spec = q_company(ctx, args.query)
    elif args.cmd == "segment":
        spec = q_segment(ctx, args)
    elif args.cmd == "book":
        spec = q_book(ctx, args)
    else:
        if len(args.queries) < 2:
            ap.error("compare needs 2 to 5 companies")
        spec = q_compare(ctx, args.queries)
    spec["as_of"] = ctx.as_of.isoformat()
    spec["licence"] = ctx.licence()
    if args.html:
        p = Path(args.html)
        p = p if p.is_absolute() else ctx.root / p
        p.parent.mkdir(parents=True, exist_ok=True)
        mc.write_text(p, to_html(spec, ctx.licence()))
        spec["html"] = mc.rel_posix(p, ctx.root)
    if args.json:
        print(json.dumps(spec, indent=2, ensure_ascii=False, default=str))
    elif args.cards:
        print(to_cards(spec))
    else:
        print(to_text(spec))
        if spec.get("html"):
            print(f"Report page: {spec['html']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
