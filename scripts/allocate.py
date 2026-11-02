"""Propose (and, on the manager's word, apply) a lead allocation (PLAN.md §10).

    python3 scripts/allocate.py                      # write today's proposal
    python3 scripts/allocate.py --dry-run            # print it, write nothing
    python3 scripts/allocate.py --exclude-rep mei --give arun:industry=logistics
    python3 scripts/allocate.py --approve all        # or --approve 1,2,5  (manager)
    python3 scripts/allocate.py --approve all --except 3,7
    python3 scripts/allocate.py --reject

How a proposal is made:
1. Hard constraints (claim.fits_rep, the same checks claim.py applies): live
   market the rep covers, territory, `max_active`, suppression, do_not_contact.
   Per run a rep gets at most min(max_active - active, daily_quota) new leads.
2. Continuity: a lead with the same `group` or website domain as an account a
   rep owns goes to that rep (or is held, with the reason).
3. p_meet: meetings / accounts contacted from log/touches.csv, smoothed with
   the beta prior in allocation.yaml: team rate <- prior; rep rate shrinks to
   the team rate; rep x industry shrinks to the rep rate (no data = parent rate).
4. EV = score x p_meet x value of the top recommended product (recommend.py;
   if none yet, the cheapest product sold in that market), in the base
   currency via markets.yaml `fx` (base currency per 1 unit of the local one).
5. Greedy: pairs by tier (A, B, C) then EV, while capacity remains.
6. Fairness: while any rep's total EV is more than `max_ev_spread` from the
   mean, move or swap the lowest-margin non-continuity lead from the top rep
   to the bottom rep if that lowers the spread.
7. Every row gets a reason; every row is re-checked before writing.
Writes log/allocation/<date>.md and .csv; never assigns anything by itself.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402
import claim as cl  # noqa: E402

CSV_FIELDS = ("row", "rep", "account", "name", "market", "tier", "score", "industry", "p_meet",
              "product", "value", "currency", "value_base", "ev", "continuity", "reason")
MEETING_STATUS = {"meeting_booked", "meeting_held"}
LAPSE_DAYS = 21


# ----------------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------------
def domain_of(meta: dict) -> str:
    d = mc.norm(meta.get("domain")).lower()
    d = re.sub(r"^https?://", "", d).split("/")[0]
    return d.removeprefix("www.")


def group_of(meta: dict) -> str:
    return re.sub(r"[^a-z0-9]+", " ", mc.norm(meta.get("group")).lower()).strip()


class Rates:
    """Smoothed meeting rates per team, rep and rep x industry."""

    def __init__(self, touches: list[dict], industry_of: dict[str, str], alpha: float, beta: float):
        self.strength = alpha + beta
        contacted: dict[tuple, set] = {}
        met: dict[tuple, set] = {}
        for t in touches:
            rep, acc = mc.norm(t.get("rep")), mc.norm(t.get("account"))
            if not rep or not acc:
                continue
            status, step = mc.norm(t.get("status")), mc.norm(t.get("step"))
            ind = industry_of.get(acc, "")
            keys = [("team",), ("rep", rep), ("ind", rep, ind)]
            if status in ("sent", "replied", *MEETING_STATUS) or step in ("first", "connect"):
                for k in keys:
                    contacted.setdefault(k, set()).add(acc)
            if status in MEETING_STATUS or step == "meeting":
                for k in keys:
                    met.setdefault(k, set()).add(acc)
                    contacted.setdefault(k, set()).add(acc)
        self.n = {k: len(v) for k, v in contacted.items()}
        self.m = {k: len(v) for k, v in met.items()}
        self.team = (self.m.get(("team",), 0) + alpha) / (self.n.get(("team",), 0) + alpha + beta)

    def _shrink(self, key: tuple, parent: float) -> float:
        return (self.m.get(key, 0) + parent * self.strength) / (self.n.get(key, 0) + self.strength)

    def rep(self, rep: str) -> float:
        return self._shrink(("rep", rep), self.team)

    def rep_ind(self, rep: str, ind: str) -> float:
        return self._shrink(("ind", rep, ind), self.rep(rep))

    def evidence(self, rep: str, ind: str) -> str:
        n, m = self.n.get(("ind", rep, ind), 0), self.m.get(("ind", rep, ind), 0)
        if n:
            return f"{m}/{n} {ind or 'all'} meetings"
        n, m = self.n.get(("rep", rep), 0), self.m.get(("rep", rep), 0)
        return f"no {ind or 'industry'} history, rep {m}/{n}" if n else "no history yet, prior"


class Valuer:
    def __init__(self, root: Path, markets: dict):
        import recommend as rc
        import score as sc

        self.rc, self.kn, self.root = rc, sc.Knowledge(root), root
        self.base = mc.norm(markets.get("base_currency")) or "SGD"
        self.fx = markets.get("fx") or {}
        self.cur = {m: mc.norm((v or {}).get("currency")) for m, v in (markets.get("markets") or {}).items()}

    def rate(self, market: str) -> float | None:
        cur = self.cur.get(market) or ""
        if not cur or cur == self.base:
            return 1.0
        r = cl._num(self.fx.get(cur))
        return r if r and r > 0 else None

    def value(self, acc: str, meta: dict, market: str) -> tuple[str, float, bool]:
        """(product id, local value, recommended?)."""
        rec = mc.as_list(meta.get("recommended"))
        prods = {mc.norm(p.get("id")): p for p in self.kn.products}
        if rec and mc.norm(rec[0]) in prods:
            pid = mc.norm(rec[0])
            v = cl._num((prods[pid].get("typical_value") or {}).get(market))
            if v:
                return pid, v, True
        r = self.rc.recommend(self.root, acc, self.kn)
        for c in r.get("candidates") or []:
            if cl._num(c.get("value")):
                return c["product"], float(c["value"]), True
        sold = [(cl._num((p.get("typical_value") or {}).get(market)), mc.norm(p.get("id")))
                for p in self.kn.products if market in [str(x) for x in mc.as_list(p.get("available_in"))]]
        sold = sorted((v, pid) for v, pid in sold if v)
        return (sold[0][1], sold[0][0], False) if sold else ("", 0.0, False)


# ----------------------------------------------------------------------------
# Proposal
# ----------------------------------------------------------------------------
def deviation(totals: dict[str, float]) -> float:
    vals = list(totals.values())
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    return 0.0 if mean <= 0 else max(abs(v - mean) for v in vals) / mean


def parse_give(specs: list[str]) -> list[tuple[str, str, str]]:
    out = []
    for s in specs or []:
        rep, _, flt = s.partition(":")
        key, eq, val = flt.partition("=")
        out.append((rep.strip(), key.strip() if eq else "id", (val if eq else key).strip().lower()))
    return out


def matches(acc: str, meta: dict, key: str, val: str) -> bool:
    if key == "id":
        return acc == mc.link_id(val)
    return mc.norm(meta.get(key)).lower() == val


def propose(root: Path, opts) -> dict:
    ctx = cl.Ctx(root)
    alloc, markets = ctx.alloc, ctx.markets
    prior = alloc.get("prior_meeting_rate") or {}
    alpha, beta = float(prior.get("alpha", 2)), float(prior.get("beta", 18))
    limit = float((alloc.get("fairness") or {}).get("max_ev_spread", 0.2))
    tiers = [t.strip().upper() for t in (opts.tiers or "A,B,C").split(",") if t.strip()]
    on = mc.today()

    reps = {rid: r for rid, r in ctx.reps.items()
            if mc.norm(r.get("role")) in ("rep", "manager") and rid not in (opts.exclude_rep or [])}
    industry_of = {a: mc.norm(p.meta.get("industry")) for a, p in ctx.accounts.items()}
    rates = Rates(mc.load_touches(root), industry_of, alpha, beta)
    valuer = Valuer(root, markets)

    active = {rid: ctx.active_count(rid) for rid in ctx.reps}
    slots = {rid: max(0, min(int(cl._num(r.get("max_active")) or 0) - active[rid],
                             int(cl._num(r.get("daily_quota")) or 0)))
             for rid, r in reps.items()}
    free = {rid: int(cl._num(r.get("max_active")) or 0) - active[rid] for rid, r in reps.items()}

    # Continuity index: group / domain -> owning rep (+ example account).
    cont: dict[str, tuple[str, str]] = {}
    for a, p in ctx.accounts.items():
        o = mc.norm(p.meta.get("owner"))
        if not o:
            continue
        for k in (("g:" + group_of(p.meta)) if group_of(p.meta) else "",
                  ("d:" + domain_of(p.meta)) if domain_of(p.meta) else ""):
            if k:
                cont.setdefault(k, (o, mc.norm(p.meta.get("name")) or a))

    gives = parse_give(opts.give)
    pool, held = [], []
    for a, p in sorted(ctx.accounts.items()):
        m = p.meta
        if mc.norm(m.get("owner")) or a in (opts.skip or []):
            continue
        if mc.norm(m.get("tier")).upper() not in tiers or not mc.is_active(m):
            continue
        why = cl.blocked(m, ctx)
        market = mc.norm(m.get("market")).upper()
        if not why and market not in ctx.live:
            why = f"market {market or '?'} is not live"
        if not why and valuer.rate(market) is None:
            why = f"fx for {valuer.cur.get(market)} is missing in markets.yaml"
        if why:
            held.append({"account": a, "market": market, "tier": mc.norm(m.get("tier")), "reason": why})
            continue
        pool.append((a, m))

    # Candidate pairs.
    leads: dict[str, dict] = {}
    for a, m in pool:
        market = mc.norm(m.get("market")).upper()
        pid, val, recd = valuer.value(a, m, market)
        lead = {"account": a, "name": mc.norm(m.get("name")) or a, "market": market,
                "tier": mc.norm(m.get("tier")).upper(), "score": cl._num(m.get("score")) or 0.0,
                "industry": industry_of[a], "product": pid, "value": val, "recommended": recd,
                "currency": valuer.cur.get(market, ""), "value_base": val * (valuer.rate(market) or 0),
                "cands": {}, "forced": None, "notes": {}}
        for k in (("g:" + group_of(m)) if group_of(m) else "", ("d:" + domain_of(m)) if domain_of(m) else ""):
            if k and k in cont:
                lead["forced"] = (cont[k][0], f"same {'group' if k[0] == 'g' else 'domain'} as {cont[k][1]}")
                break
        for rep_id, key, val_ in gives:
            if matches(a, m, key, val_):
                lead["forced"] = (rep_id, f"manager: {key}={val_} to {rep_id}" if key != "id" else
                                  f"manager picked {rep_id}")
        no_fit = []
        for rid, r in reps.items():
            ok, why, notes = cl.fits_rep(m, r, ctx)
            if ok:
                p_meet = rates.rep_ind(rid, lead["industry"])
                lead["cands"][rid] = lead["score"] * p_meet * lead["value_base"]
                lead["notes"][rid] = (p_meet, notes)
            else:
                no_fit.append(f"{rid}: {why}")
        lead["no_fit"] = no_fit
        leads[a] = lead

    assign: dict[str, str] = {}
    load = {rid: 0 for rid in reps}

    def give(a: str, rid: str) -> None:
        assign[a] = rid
        load[rid] += 1

    unassigned = []
    # 1. Continuity and manager picks first.
    for a, L in sorted(leads.items(), key=lambda kv: (mc.TIERS.index(kv[1]["tier"]) if kv[1]["tier"] in mc.TIERS else 9,
                                                      -kv[1]["score"])):
        if not L["forced"]:
            continue
        rid, why = L["forced"]
        if rid not in L["cands"]:
            reason = next((x for x in L["no_fit"] if x.startswith(rid + ":")), f"{rid}: not an active rep")
            unassigned.append({"account": a, "market": L["market"], "tier": L["tier"],
                               "reason": f"held for {rid} ({why}) but {reason.split(': ', 1)[-1]}"})
        elif load[rid] >= slots.get(rid, 0):
            unassigned.append({"account": a, "market": L["market"], "tier": L["tier"],
                               "reason": f"held for {rid} ({why}); no slots left this run"})
        else:
            give(a, rid)
    # 2. Greedy by tier, then EV.
    pairs = sorted(((mc.TIERS.index(L["tier"]) if L["tier"] in mc.TIERS else 9, -ev, a, rid)
                    for a, L in leads.items() if not L["forced"] for rid, ev in L["cands"].items()))
    for _, _, a, rid in pairs:
        if a in assign or load[rid] >= slots.get(rid, 0):
            continue
        give(a, rid)
    for a, L in leads.items():
        if a in assign or L["forced"]:
            continue
        if not L["cands"]:
            reason = "; ".join(L["no_fit"]) or "no active rep"
        else:
            reason = "no free slots this run for " + ", ".join(sorted(L["cands"]))
        unassigned.append({"account": a, "market": L["market"], "tier": L["tier"], "reason": reason})

    # 3. Fairness.
    def totals() -> dict[str, float]:
        # Only reps who could receive a lead this run are compared.
        t = {rid: 0.0 for rid in reps if slots.get(rid, 0) > 0
             and any(rid in L["cands"] for L in leads.values())}
        for a, rid in assign.items():
            t[rid] = t.get(rid, 0.0) + leads[a]["cands"][rid]
        return t

    before = deviation(totals())
    moves = []
    for _ in range(200):
        t = totals()
        if deviation(t) <= limit or len(t) < 2:
            break
        top, bot = max(t, key=t.get), min(t, key=t.get)
        best = None
        cur = deviation(t)
        tops = [a for a, r in assign.items() if r == top and not leads[a]["forced"]]
        bots = [a for a, r in assign.items() if r == bot and not leads[a]["forced"]]
        for a in tops:
            if bot not in leads[a]["cands"]:
                continue
            margin = leads[a]["cands"][top] - leads[a]["cands"][bot]
            if load[bot] < slots.get(bot, 0):
                nt = dict(t)
                nt[top] -= leads[a]["cands"][top]
                nt[bot] += leads[a]["cands"][bot]
                d = deviation(nt)
                if d < cur and (best is None or (margin, d) < best[0]):
                    best = ((margin, d), ("move", a, None))
            for b in bots:
                if top not in leads[b]["cands"]:
                    continue
                m2 = margin + leads[b]["cands"][bot] - leads[b]["cands"][top]
                nt = dict(t)
                nt[top] += leads[b]["cands"][top] - leads[a]["cands"][top]
                nt[bot] += leads[a]["cands"][bot] - leads[b]["cands"][bot]
                d = deviation(nt)
                if d < cur and (best is None or (m2, d) < best[0]):
                    best = ((m2, d), ("swap", a, b))
        if best is None:
            break
        kind, a, b = best[1]
        if kind == "move":
            assign[a] = bot
            load[top] -= 1
            load[bot] += 1
            moves.append(f"moved {a} {top} -> {bot}")
        else:
            assign[a], assign[b] = bot, top
            moves.append(f"swapped {a} ({top} -> {bot}) with {b} ({bot} -> {top})")
    after = deviation(totals())

    # 4. Rows with reasons.
    rows = []
    order = sorted(assign.items(), key=lambda kv: (leads[kv[0]]["market"], kv[1],
                                                   mc.TIERS.index(leads[kv[0]]["tier"]) if leads[kv[0]]["tier"] in mc.TIERS else 9,
                                                   -leads[kv[0]]["cands"][kv[1]], kv[0]))
    for i, (a, rid) in enumerate(order, 1):
        L = leads[a]
        p_meet, notes = L["notes"][rid]
        name = mc.norm(reps[rid].get("name")).split(" ")[0] or rid
        parts = [f"{name}: {L['industry'] or 'industry ?'} meeting rate {p_meet:.0%} vs team {rates.team:.0%} "
                 f"({rates.evidence(rid, L['industry'])})",
                 f"{free[rid]} slots free"]
        if L["forced"]:
            parts.append(L["forced"][1])
        if len(L["cands"]) == 1:
            parts.append("only rep who fits")
        parts.append(f"top product {L['product']} ({L['currency']} {L['value']:,.0f})" if L["recommended"]
                     else f"no recommendation yet, floor {L['product']} ({L['currency']} {L['value']:,.0f})")
        parts += notes
        rows.append({"row": i, "rep": rid, "account": a, "name": L["name"], "market": L["market"],
                     "tier": L["tier"], "score": round(L["score"], 3), "industry": L["industry"],
                     "p_meet": round(p_meet, 4), "product": L["product"], "value": L["value"],
                     "currency": L["currency"], "value_base": round(L["value_base"], 2),
                     "ev": round(L["cands"][rid], 2), "continuity": L["forced"][1] if L["forced"] else "",
                     "reason": "; ".join(parts)})

    return {"date": on.isoformat(), "base": valuer.base, "limit": limit, "spread_before": round(before, 4),
            "spread": round(after, 4), "fair_moves": moves, "team_rate": round(rates.team, 4),
            "reps": {rid: {"active": active[rid], "max_active": int(cl._num(r.get("max_active")) or 0),
                           "slots": slots[rid], "markets": mc.as_list(r.get("markets"))}
                     for rid, r in reps.items()},
            "rows": rows, "unassigned": unassigned + held, "rebalance": rebalance(root, ctx, on),
            "checks": verify(rows, ctx, slots)}


def rebalance(root: Path, ctx: cl.Ctx, on) -> list[dict]:
    last: dict[str, object] = {}
    for t in mc.load_touches(root):
        d = mc.to_date(t.get("ts"))
        a = mc.norm(t.get("account"))
        if d and a and (a not in last or d > last[a]):
            last[a] = d
    out = []
    for a, p in sorted(ctx.accounts.items()):
        m = p.meta
        o = mc.norm(m.get("owner"))
        if not o or not mc.is_active(m):
            continue
        rep = ctx.reps.get(o)
        if rep is None or mc.norm(rep.get("role")) == "inactive":
            out.append({"account": a, "owner": o, "flag": "owner_inactive",
                        "action": f"python3 scripts/claim.py --reassign {o} <rep> {a}"})
            continue
        claimed = [d for d in (mc.to_date(m.get("claimed_on")), mc.to_date(m.get("allocated_on"))) if d]
        if not claimed:
            continue
        ref = max(claimed + [d for d in (mc.to_date(m.get("last_touch")), last.get(a)) if d])
        if (on - ref).days > LAPSE_DAYS:
            out.append({"account": a, "owner": o, "flag": f"lapsed ({(on - ref).days} days, no touch)",
                        "action": f"python3 scripts/claim.py --release {a}"})
    for rid, r in ctx.reps.items():
        cap = int(cl._num(r.get("max_active")) or 0)
        n = ctx.active_count(rid)
        if cap and n > cap:
            out.append({"account": "", "owner": rid, "flag": f"overloaded ({n}/{cap})",
                        "action": f"python3 scripts/claim.py --reassign {rid} <rep> <ids of {n - cap} lowest-score new accounts>"})
    return out


def verify(rows: list[dict], ctx: cl.Ctx, slots: dict[str, int]) -> list[dict]:
    """Re-check every row against the hard constraints, independently of the algorithm."""
    count: dict[str, int] = {}
    seen: set[str] = set()
    bad = {"market": [], "territory": [], "capacity": [], "suppression/DNC": [], "unowned": [], "once": []}
    for r in rows:
        a, rid = r["account"], r["rep"]
        meta, rep = ctx.accounts[a].meta, ctx.reps[rid]
        count[rid] = count.get(rid, 0) + 1
        if a in seen:
            bad["once"].append(a)
        seen.add(a)
        if mc.norm(meta.get("owner")):
            bad["unowned"].append(a)
        if r["market"] not in ctx.live or r["market"] not in [str(m).upper() for m in mc.as_list(rep.get("markets"))]:
            bad["market"].append(a)
        if not cl.territory_fit(meta, rep)[0]:
            bad["territory"].append(a)
        if cl.blocked(meta, ctx):
            bad["suppression/DNC"].append(a)
    for rid, n in count.items():
        cap = int(cl._num(ctx.reps[rid].get("max_active")) or 0)
        if n > slots.get(rid, 0) or ctx.active_count(rid) + n > cap:
            bad["capacity"].append(rid)
    desc = {"market": "live market the rep covers", "territory": "inside rep territory",
            "capacity": "within free slots and daily quota", "suppression/DNC": "no suppressed / DNC lead",
            "unowned": "lead still unowned", "once": "each lead at most once"}
    return [{"check": desc[k], "ok": not v, "violations": v} for k, v in bad.items()]


# ----------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------
def out_path(root: Path, date: str) -> Path:
    folder = root / "log" / "allocation"
    n = 1
    while True:
        p = folder / (f"{date}.md" if n == 1 else f"{date}-{n}.md")
        if not p.is_file():
            return p
        page = mc.read_page(p, root)
        if mc.norm(((page.meta if page else None) or {}).get("status")) in ("", "proposed"):
            return p
        n += 1


def latest_proposal(root: Path, date: str | None) -> Path | None:
    folder = root / "log" / "allocation"
    files = sorted(folder.glob(f"{date or '*'}*.md")) if folder.is_dir() else []
    files = [f for f in files if (mc.read_page(f, root) or None) and
             mc.norm((mc.read_page(f, root).meta or {}).get("type")) == "allocation"]
    return files[-1] if files else None


def render(P: dict, user: str) -> str:
    rows, base = P["rows"], P["base"]
    by_rep: dict[tuple, dict] = {}
    for r in rows:
        k = (r["market"], r["rep"])
        s = by_rep.setdefault(k, {"A": 0, "B": 0, "C": 0, "ev": 0.0, "n": 0})
        s[r["tier"]] = s.get(r["tier"], 0) + 1
        s["ev"] += r["ev"]
        s["n"] += 1
    L = [f"# Allocation proposal · {P['date']}", "",
         f"{len(rows)} leads to {len({r['rep'] for r in rows})} rep(s). EV in {base}. "
         f"EV spread {P['spread']:.0%} (limit {P['limit']:.0%})"
         + (f", was {P['spread_before']:.0%} before {len(P['fair_moves'])} fairness move(s)" if P["fair_moves"] else "")
         + f". Team meeting rate {P['team_rate']:.1%} (smoothed).", "",
         "Approve in one sentence: \"approve all\", \"approve except 3 and 7\", or an edit "
         "(\"give the logistics ones to Arun\").", "", "## Per rep", "",
         "| Market | Rep | Leads | A | B | C | EV (" + base + ") | Active / max | Slots this run |",
         "|---|---|---|---|---|---|---|---|---|"]
    for (mk, rid), s in sorted(by_rep.items()):
        rp = P["reps"][rid]
        L.append(f"| {mk} | {rid} | {s['n']} | {s['A']} | {s['B']} | {s['C']} | {s['ev']:,.0f} | "
                 f"{rp['active']} / {rp['max_active']} | {rp['slots']} |")
    L += ["", "## Rows", "", "| # | Rep | Account | Mkt | Tier | Score | Product | EV | Reason |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['row']} | {r['rep']} | [[accounts/{r['account']}]] | {r['market']} | {r['tier']} | "
                 f"{r['score']:.2f} | {r['product']} | {r['ev']:,.0f} | {r['reason']} |")
    L += ["", "## Constraints holding", "", "| Check | Result |", "|---|---|"]
    for c in P["checks"]:
        L.append(f"| {c['check']} | {'ok' if c['ok'] else 'VIOLATED: ' + ', '.join(c['violations'])} |")
    L.append(f"| EV spread ≤ {P['limit']:.0%} | {'ok' if P['spread'] <= P['limit'] else 'over limit: no improving move left'} ({P['spread']:.0%}) |")
    L += ["", "## Not assigned", ""]
    groups: dict[str, list[str]] = {}
    for u in P["unassigned"]:
        groups.setdefault(u["reason"], []).append(f"{u['account']} ({u['tier']})")
    for reason, accs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        L.append(f"- {len(accs)} × {reason}: " + ", ".join(accs[:12]) + (" …" if len(accs) > 12 else ""))
    if not groups:
        L.append("- none")
    L += ["", "## Rebalancing", ""]
    for b in P["rebalance"]:
        L.append(f"- {b['owner']} · {b['account'] or '-'} · {b['flag']} → `{b['action']}`")
    if not P["rebalance"]:
        L.append("- none: no lapsed claims, overloaded reps or inactive owners")
    if P["fair_moves"]:
        L += ["", "## Fairness moves", ""] + [f"- {m}" for m in P["fair_moves"]]
    L.append("")
    meta = {"type": "allocation", "date": P["date"], "status": "proposed", "created_by": user,
            "leads": len(rows), "spread": P["spread"], "limit": P["limit"], "base_currency": base}
    return mc.compose_page(meta, "\n".join(L))


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# Approval
# ----------------------------------------------------------------------------
def parse_ids(text: str | None) -> set[int]:
    out = set()
    for part in re.split(r"[,\s]+", text or ""):
        if re.fullmatch(r"\d+-\d+", part):
            a, b = map(int, part.split("-"))
            out.update(range(a, b + 1))
        elif part.isdigit():
            out.add(int(part))
    return out


def approve(root: Path, user: dict, which: str, exclude: str | None, date: str | None, reject: bool) -> dict:
    md = latest_proposal(root, date)
    if md is None:
        return {"error": "no allocation proposal found; run allocate.py first"}
    page = mc.read_page(md, root)
    status = mc.norm(page.meta.get("status"))
    if status not in ("", "proposed"):
        return {"error": f"{md.name} is already {status}"}
    rows = mc.read_csv(md.with_suffix(".csv"))
    if reject:
        mc.update_frontmatter(md, {"status": "rejected", "decided_by": user["id"], "decided_on": mc.today().isoformat()})
        mc.write_text(md, mc.read_text(md).rstrip("\n") + f"\n\n## Decisions\n\n- Rejected by {user['id']} on {mc.today()}.\n")
        mc.append_log("allocate", user["id"], f"log/allocation/{md.stem}", "proposal rejected")
        return {"proposal": md.name, "status": "rejected", "applied": [], "rejected": []}
    want = {int(r["row"]) for r in rows} if which.strip().lower() == "all" else parse_ids(which)
    want -= parse_ids(exclude)
    chosen = [r for r in rows if int(r["row"]) in want]
    ops = [{"op": "assign", "account": r["account"], "rep": r["rep"], "note": f"allocation {md.stem} row {r['row']}"}
           for r in chosen]
    res = cl.apply(root, ops, user) if ops else {"applied": [], "rejected": [], "message": "no rows chosen"}
    done = {o["account"] for o in res["applied"]}
    skipped = sorted(int(r["row"]) for r in rows if int(r["row"]) not in want)
    new_status = "applied" if len(done) == len(rows) else ("partial" if done else "rejected")
    lines = [f"- {mc.now_stamp()} {user['id']}: approved {len(done)} of {len(rows)} rows"]
    if skipped:
        lines.append(f"- Not approved: rows {', '.join(map(str, skipped))}")
    for r in res["rejected"]:
        lines.append(f"- Refused by claim.py: {r['account']} — {r['reason']}")
    mc.update_frontmatter(md, {"status": new_status, "decided_by": user["id"], "decided_on": mc.today().isoformat()})
    mc.write_text(md, mc.read_text(md).rstrip("\n") + "\n\n## Decisions\n\n" + "\n".join(lines) + "\n")
    tiers: dict[str, int] = {}
    for r in chosen:
        if r["account"] in done:
            tiers[r["tier"]] = tiers.get(r["tier"], 0) + 1
    mix = ", ".join(f"{t} {n}" for t, n in sorted(tiers.items()))
    mc.append_log("assign", user["id"], f"log/allocation/{md.stem}",
                  f"{len(done)} assigned ({mix or 'none'}), {len(res['rejected'])} rejected")
    return {"proposal": md.name, "status": new_status, "applied": sorted(done),
            "rejected": res["rejected"], "message": res.get("message", "")}


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def print_summary(P: dict, path: str | None) -> None:
    print(f"Allocation proposal {P['date']}: {len(P['rows'])} leads, EV spread {P['spread']:.0%} "
          f"(limit {P['limit']:.0%}), base {P['base']}" + (f" -> {path}" if path else " (dry run)"))
    for rid, rp in P["reps"].items():
        mine = [r for r in P["rows"] if r["rep"] == rid]
        tiers = {t: sum(1 for r in mine if r["tier"] == t) for t in mc.TIERS}
        print(f"  {rid}: {len(mine)} leads (A {tiers['A']}, B {tiers['B']}, C {tiers['C']}), "
              f"EV {sum(r['ev'] for r in mine):,.0f} {P['base']}; active {rp['active']}/{rp['max_active']}, "
              f"slots this run {rp['slots']}")
    for r in P["rows"]:
        print(f"  {r['row']:>3}. {r['rep']:<8} {r['account']:<34} {r['market']} {r['tier']} "
              f"score {r['score']:.2f}  EV {r['ev']:>7,.0f}  {r['reason']}")
    print("Constraints:")
    for c in P["checks"]:
        print(f"  [{'ok' if c['ok'] else 'FAIL'}] {c['check']}" + ("" if c["ok"] else f": {c['violations']}"))
    print(f"  [{'ok' if P['spread'] <= P['limit'] else 'over'}] EV spread {P['spread']:.0%} ≤ {P['limit']:.0%}")
    groups: dict[str, int] = {}
    for u in P["unassigned"]:
        groups[u["reason"]] = groups.get(u["reason"], 0) + 1
    if groups:
        print("Not assigned:")
        for reason, n in sorted(groups.items(), key=lambda kv: -kv[1]):
            print(f"  {n} × {reason}")
    for b in P["rebalance"]:
        print(f"Rebalance: {b['owner']} {b['account']} {b['flag']} -> {b['action']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Propose a lead allocation across reps (PLAN.md §10), or apply "
                                             "the manager's approval of one.")
    ap.add_argument("--dry-run", action="store_true", help="print the proposal, write nothing")
    ap.add_argument("--json", action="store_true", help="print JSON")
    ap.add_argument("--tiers", default="A,B,C", help="tiers to allocate (default A,B,C)")
    ap.add_argument("--exclude-rep", action="append", metavar="REP", help="give this rep nothing (repeatable)")
    ap.add_argument("--give", action="append", metavar="REP:FILTER",
                    help="force matching leads to REP (hard constraints still apply); FILTER is an account id "
                         "or industry=x / tier=A / market=SG (repeatable)")
    ap.add_argument("--skip", action="append", metavar="ID", help="leave this lead out (repeatable)")
    ap.add_argument("--approve", metavar="all|ROWS", help="manager: assign these rows (e.g. all, 1,2,5, 1-4)")
    ap.add_argument("--except", dest="exclude", metavar="ROWS", help="with --approve: rows to leave out")
    ap.add_argument("--reject", action="store_true", help="manager: reject the latest proposal")
    ap.add_argument("--date", help="proposal date for --approve/--reject (default: latest)")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    user = mc.current_user(root)
    if not user or mc.norm(user.get("role")) != "manager":
        print("allocate.py is for the manager (role: manager in reps/<id>.md).")
        return 1
    if args.approve or args.reject:
        res = approve(root, user, args.approve or "", args.exclude, args.date, args.reject)
        if args.json:
            print(json.dumps(res, indent=2, default=str))
        elif res.get("error"):
            print(res["error"])
        else:
            print(f"{res['proposal']}: {res['status']}. Assigned {len(res['applied'])}: {', '.join(res['applied']) or '-'}")
            for r in res["rejected"]:
                print(f"  refused: {r['account']} — {r['reason']}")
            if res.get("message"):
                print(f"  ({res['message']})")
        return 1 if res.get("error") else 0
    P = propose(root, args)
    if not all(c["ok"] for c in P["checks"]):
        print_summary(P, None)
        print("ERROR: a proposed row breaks a hard constraint; nothing written.")
        return 2
    path = None
    if not args.dry_run:
        md = out_path(root, P["date"])
        mc.write_text(md, render(P, user["id"]))
        mc.write_text(md.with_suffix(".csv"), to_csv(P["rows"]))
        path = mc.rel_posix(md, root)
        reps_n = len({r["rep"] for r in P["rows"]})
        mc.append_log("allocate", user["id"], path.removesuffix(".md"),
                      f"proposal: {len(P['rows'])} leads, {reps_n} reps, spread {P['spread']:.0%}")
    if args.json:
        print(json.dumps({**P, "path": path}, indent=2, default=str))
    else:
        print_summary(P, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
