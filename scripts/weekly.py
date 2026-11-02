"""Numbers for mama-weekly: metrics, funnel, score calibration, allocation
fairness, lapsed claims and retention. Read-only; the skill adds the judgement.

- Week = ISO week (default: the one containing today); trailing = the 4 weeks
  before it; calibration = the 8 weeks ending with it.
- Metrics come from log/touches.csv joined to account pages (tier, industry,
  market, pains, signals) and contact pages (persona). Sent = touches with
  status `sent`; replies = `step: reply` rows except out_of_office/bounce;
  positive = interested, meeting_request, referral; meetings = distinct
  accounts with meeting_booked or meeting_held. Rates for any cell with fewer
  than 20 sent are "insufficient data".
- Calibration: meeting rate by current tier over contacted accounts. Verdict
  `insufficient` (any of A or C under 20), `propose` (A < 2x C) or `ok`.
- Allocation: each log/allocation/*.md proposal's status, EV spread vs limit
  and any VIOLATED constraint; rep x industry conversion smoothed with
  allocation.yaml prior_meeting_rate (allocate.Rates); lapsed claims (owned,
  no touch for 21 days).

    python3 scripts/weekly.py                 # this week, markdown
    python3 scripts/weekly.py --week 2026-W45 --json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402

MIN_N = 20
POSITIVE = {"interested", "meeting_request", "referral"}
NOT_A_REPLY = {"out_of_office", "bounce"}
MEETING_STATUS = {"meeting_booked", "meeting_held"}
DIMS = ("rep", "pattern", "persona", "pain", "signal", "product", "tier", "market")
INSUFFICIENT = "insufficient data"


def week_bounds(week: str | None, on: dt.date) -> tuple[str, dt.date, dt.date]:
    if week:
        m = re.fullmatch(r"(\d{4})-W(\d{1,2})", week.strip())
        if not m:
            raise ValueError(f"--week must look like 2026-W45, got {week!r}")
        start = dt.date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
    else:
        start = on - dt.timedelta(days=on.weekday())
    y, w, _ = start.isocalendar()
    return f"{y}-W{w:02d}", start, start + dt.timedelta(days=6)


def rate(num: int, n: int) -> float | str:
    return round(num / n, 4) if n >= MIN_N else INSUFFICIENT


class Book:
    """Account and contact attributes used to cut touches."""

    def __init__(self, root: Path):
        self.acc = {p.id: p.meta for p in mc.iter_pages("account", root)}
        self.persona = {p.id: mc.norm(p.meta.get("persona")) for p in mc.iter_pages("contact", root)}

    def keys(self, t: dict) -> dict[str, list[str]]:
        m = self.acc.get(mc.norm(t.get("account")), {})
        return {
            "rep": [mc.norm(t.get("rep"))],
            "pattern": [mc.norm(t.get("pattern"))],
            "persona": [self.persona.get(mc.norm(t.get("contact")), "")],
            "pain": [mc.norm(x) for x in mc.as_list(m.get("pains"))],
            "signal": [mc.norm(x) for x in mc.as_list(m.get("signals"))],
            "product": [p.strip() for p in mc.norm(t.get("products")).split(";") if p.strip()],
            "tier": [mc.norm(m.get("tier"))],
            "market": [mc.norm(m.get("market"))],
        }


def metrics(touches: list[dict], book: Book, start: dt.date, end: dt.date) -> dict:
    rows = [t for t in touches if (d := mc.to_date(t.get("ts"))) and start <= d <= end]

    def cell():
        return {"sent": 0, "replies": 0, "positive": 0, "_met": set()}

    total, cuts = cell(), {d: {} for d in DIMS}
    for t in rows:
        status, step, cls = mc.norm(t.get("status")), mc.norm(t.get("step")), mc.norm(t.get("reply_class"))
        sent = status == "sent"
        reply = step == "reply" and cls not in NOT_A_REPLY
        pos = reply and cls in POSITIVE
        met = mc.norm(t.get("account")) if status in MEETING_STATUS else ""
        targets = [total]
        for dim, vals in book.keys(t).items():
            for v in vals or [""]:
                targets.append(cuts[dim].setdefault(v or "(none)", cell()))
        for c in targets:
            c["sent"] += sent
            c["replies"] += reply
            c["positive"] += pos
            if met:
                c["_met"].add(met)

    def done(c: dict) -> dict:
        meetings = len(c.pop("_met"))
        return {**c, "meetings": meetings, "reply_rate": rate(c["replies"], c["sent"]),
                "meeting_rate": rate(meetings, c["sent"])}

    return {"from": start.isoformat(), "to": end.isoformat(), "touches": len(rows), "total": done(total),
            "cuts": {d: {k: done(v) for k, v in sorted(cs.items())} for d, cs in cuts.items()}}


def funnel(root: Path, book: Book, start: dt.date) -> dict:
    now = Counter(mc.norm(m.get("stage")) or "new" for m in book.acc.values())
    code, rev, _ = mc.run_git(["rev-list", "-1", f"--before={start.isoformat()} 00:00", "HEAD"], cwd=root)
    before: dict | None = None
    if code == 0 and rev.strip():
        code, out, _ = mc.run_git(["grep", "-h", "-E", "^stage:", rev.strip(), "--", "wiki/accounts/"], cwd=root)
        if code in (0, 1):
            before = dict(Counter(line.split(":", 1)[1].strip() or "new" for line in out.splitlines()))
    stages = list(mc.STAGES) + sorted(set(now) - set(mc.STAGES))
    return {"week_ago_rev": rev.strip()[:10] if before is not None else None,
            "stages": {s: {"now": now.get(s, 0), "week_ago": None if before is None else before.get(s, 0)}
                       for s in stages}}


def calibration(touches: list[dict], book: Book, start: dt.date, end: dt.date) -> dict:
    contacted: dict[str, set] = {t: set() for t in mc.TIERS}
    met: dict[str, set] = {t: set() for t in mc.TIERS}
    for t in touches:
        d = mc.to_date(t.get("ts"))
        acc = mc.norm(t.get("account"))
        tier = mc.norm(book.acc.get(acc, {}).get("tier"))
        if not d or not (start <= d <= end) or tier not in contacted:
            continue
        status = mc.norm(t.get("status"))
        if status in ("sent", *MEETING_STATUS):
            contacted[tier].add(acc)
        if status in MEETING_STATUS:
            met[tier].add(acc)
    table = {t: {"contacted": len(contacted[t]), "meetings": len(met[t]),
                 "meeting_rate": rate(len(met[t]), len(contacted[t]))} for t in mc.TIERS}
    a, c = table["A"]["meeting_rate"], table["C"]["meeting_rate"]
    if INSUFFICIENT in (a, c):
        verdict, lift = "insufficient", None
    else:
        lift = round(a / c, 2) if c else None
        verdict = "ok" if (c == 0 and a > 0) or (lift is not None and lift >= 2) else "propose"
    return {"from": start.isoformat(), "to": end.isoformat(), "tiers": table, "lift_a_over_c": lift,
            "verdict": verdict, "note": "tier is each account's current tier"}


def allocation(root: Path, book: Book, touches: list[dict], on: dt.date) -> dict:
    import allocate as al
    import lint

    proposals = []
    for p in sorted((root / "log" / "allocation").glob("*.md")):
        page = mc.read_page(p, root)
        if not page or not page.meta:
            continue
        m = page.meta
        spread, limit = float(m.get("spread") or 0), float(m.get("limit") or 0)
        violated = [ln.split("|")[1].strip() for ln in page.body.splitlines()
                    if ln.startswith("|") and "VIOLATED" in ln]
        proposals.append({"file": page.rel, "date": mc.norm(m.get("date")), "status": mc.norm(m.get("status")),
                          "leads": m.get("leads"), "spread": spread, "limit": limit,
                          "spread_ok": spread <= limit, "violations": violated})
    alloc = mc.load_yaml(root / "knowledge" / "allocation.yaml", {}) or {}
    prior = alloc.get("prior_meeting_rate") or {}
    industry_of = {a: mc.norm(m.get("industry")) for a, m in book.acc.items()}
    rates = al.Rates(touches, industry_of, float(prior.get("alpha", 2)), float(prior.get("beta", 18)))
    conversion = []
    for (kind, *rest), n in sorted(rates.n.items()):
        if kind != "ind":
            continue
        rep, ind = rest
        conversion.append({"rep": rep, "industry": ind or "(none)", "contacted": n,
                           "meetings": rates.m.get(("ind", rep, ind), 0),
                           "smoothed_rate": round(rates.rep_ind(rep, ind), 4)})
    last = lint.last_touch_dates(touches)
    lapsed = []
    for acc, m in sorted(book.acc.items()):
        if not mc.norm(m.get("owner")) or not mc.is_active(m):
            continue
        claimed = [d for d in (mc.to_date(m.get("claimed_on")), mc.to_date(m.get("allocated_on"))) if d]
        if not claimed:
            continue
        ref = max(claimed + [d for d in (mc.to_date(m.get("last_touch")), last.get(acc)) if d])
        if (on - ref).days > lint.IDLE_DAYS:
            lapsed.append({"account": acc, "owner": mc.norm(m.get("owner")), "idle_days": (on - ref).days})
    return {"team_rate": round(rates.team, 4), "proposals": proposals, "conversion": conversion, "lapsed": lapsed,
            "violations": sum(len(p["violations"]) for p in proposals)}


def retention(root: Path, on: dt.date) -> dict:
    import lint

    out = {}
    for folder, days in lint.retention_rules(root).items():
        base = root / folder
        files = sorted(mc.rel_posix(p, root) for p in base.rglob("*")
                       if p.is_file() and p.name != ".gitkeep"
                       and (d := lint._file_date(p, root)) and (on - d).days > days) if base.is_dir() else []
        out[folder] = {"days": days, "expired": files}
    return out


def build(root: Path, week: str | None = None) -> dict:
    on = mc.today()
    label, start, end = week_bounds(week, on)
    book, touches = Book(root), mc.load_touches(root)
    return {
        "week": label, "from": start.isoformat(), "to": end.isoformat(), "min_n": MIN_N,
        "metrics": {"week": metrics(touches, book, start, end),
                    "trailing_4w": metrics(touches, book, start - dt.timedelta(days=28), start - dt.timedelta(days=1))},
        "funnel": funnel(root, book, start),
        "calibration": calibration(touches, book, end - dt.timedelta(days=55), end),
        "allocation": allocation(root, book, touches, on),
        "retention": retention(root, on),
    }


def _fmt(v) -> str:
    return f"{v:.0%}" if isinstance(v, float) else str(v)


def render(R: dict) -> str:
    L = [f"# Weekly numbers · {R['week']} ({R['from']} to {R['to']})", ""]
    for key, name in (("week", "This week"), ("trailing_4w", "Trailing 4 weeks")):
        M = R["metrics"][key]
        t = M["total"]
        L += [f"## Metrics · {name} ({M['from']} to {M['to']})", "",
              f"Sent {t['sent']}, replies {t['replies']} ({_fmt(t['reply_rate'])}), positive {t['positive']}, "
              f"meetings {t['meetings']} ({_fmt(t['meeting_rate'])}).", ""]
        for dim, cells in M["cuts"].items():
            if not cells:
                continue
            L += [f"| {dim} | sent | replies | reply rate | meetings | meeting rate |", "|---|---|---|---|---|---|"]
            L += [f"| {k} | {c['sent']} | {c['replies']} | {_fmt(c['reply_rate'])} | {c['meetings']} | "
                  f"{_fmt(c['meeting_rate'])} |" for k, c in cells.items()]
            L.append("")
    F = R["funnel"]
    L += ["## Funnel", "", f"| stage | now | week ago ({F['week_ago_rev'] or 'no history'}) |", "|---|---|---|"]
    L += [f"| {s} | {v['now']} | {'-' if v['week_ago'] is None else v['week_ago']} |" for s, v in F["stages"].items()]
    C = R["calibration"]
    L += ["", f"## Calibration ({C['from']} to {C['to']})", "", "| tier | contacted | meetings | meeting rate |",
          "|---|---|---|---|"]
    L += [f"| {t} | {v['contacted']} | {v['meetings']} | {_fmt(v['meeting_rate'])} |" for t, v in C["tiers"].items()]
    L += ["", f"Lift A/C: {C['lift_a_over_c'] if C['lift_a_over_c'] is not None else '-'} · verdict: **{C['verdict']}**", ""]
    A = R["allocation"]
    L += ["## Allocation", "", "| proposal | status | leads | EV spread | limit | violations |", "|---|---|---|---|---|---|"]
    L += [f"| {p['file']} | {p['status']} | {p['leads']} | {p['spread']:.0%}{'' if p['spread_ok'] else ' OVER'} | "
          f"{p['limit']:.0%} | {', '.join(p['violations']) or 0} |" for p in A["proposals"]]
    L += ["", f"Team meeting rate (smoothed): {A['team_rate']:.1%}.", ""]
    if A["conversion"]:
        L += ["| rep | industry | contacted | meetings | smoothed rate |", "|---|---|---|---|---|"]
        L += [f"| {c['rep']} | {c['industry']} | {c['contacted']} | {c['meetings']} | {c['smoothed_rate']:.1%} |"
              for c in A["conversion"]]
        L.append("")
    L.append("Lapsed claims: " + (", ".join(f"{x['account']} ({x['owner']}, {x['idle_days']}d)" for x in A["lapsed"])
                                  or "none"))
    L += ["", "## Retention", ""]
    for folder, v in R["retention"].items():
        L.append(f"- {folder} ({v['days']} days): {len(v['expired'])} expired"
                 + (f", e.g. {v['expired'][0]}" if v["expired"] else ""))
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Weekly metrics, funnel, calibration, allocation fairness and "
                                             "retention for mama-weekly. Writes nothing.")
    ap.add_argument("--week", help="ISO week, e.g. 2026-W45 (default: this week)")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    try:
        R = build(mc.repo_root(), args.week)
    except ValueError as exc:
        print(exc)
        return 1
    print(json.dumps(R, indent=2) if args.json else render(R), end="" if not args.json else "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
