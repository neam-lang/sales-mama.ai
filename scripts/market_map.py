"""Market map: Singapore market questions answered as data for the 3D Insights scene (spec §4–5).

    python3 scripts/market_map.py overview --segment clinics                # island, regions, headline metrics
    python3 scripts/market_map.py area     --segment clinics --area tampines   # one planning area or region
    python3 scripts/market_map.py rank     --segment clinics --by whitespace --top 10
  segment: --segment <ICP industry> | --ssic <prefix> | nothing (all live companies)
  scope:   --owner me (default) | team (manager only) | <rep id>   -> whose accounts count as "ours"
  every command: --height <measure> --colour <measure> --exclude-hubs --out company-check/reports/map-<slug>.json

Every number is computed here from company-check/data/registry.sqlite (ACRA via data.gov.sg), the account pages
and knowledge/geo/ (planning areas, postal placement; scripts/build_geo.py). The model only chooses the question
and explains the result; it never types a number, a height or a coordinate (ADR-0003, ADR-0009).

Output: the company_analytics shape {title, summary[], as_of, licence, order[], sections{}} plus one section
  map3d  segment, height{key,label,unit}, colour{key,label,breaks[],scheme}, areas[{id,name,region,values{},approx}],
         focus[], camera, halos[], accounts[], method{}
Counts in an area are estimates when a company's exact postal code is not a known point ("approx": true, shown
as "≈"); area counts always add up exactly to the segment total (largest remainder).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import company_analytics as ca  # noqa: E402
import mama_common as mc  # noqa: E402

GEO = Path("knowledge/geo")
TOUCHED = ("contacted", "replied", "meeting", "handed_over")   # stage >= contacted
CUSTOMER = ("handed_over",)                                     # won and handed to delivery
MIN_AREA = 5            # fewer companies than this: rates and medians are "too few"
MIN_GROWTH_BASE = 20    # growth needs at least this many registrations in the prior 12 months
HUB = 300               # a postal code with this many live registrations is a registration hub (273 codes, 2026-10)

MEASURES = {
    "base":        ("Live companies", "companies"),
    "addressable": ("Addressable", "companies"),
    "density":     ("Companies per km²", "per km²"),
    "growth":      ("New registrations vs prior year", "%"),
    "age":         ("Median age", "yrs"),
    "ontime":      ("Filing on time", "%"),
    "accounts":    ("Our accounts", "accounts"),
    "customers":   ("Customers", "accounts"),
    "penetration": ("Penetration", "%"),
    "coverage":    ("Coverage", "%"),
    "whitespace":  ("Whitespace", "companies"),
    "hubs":        ("At registration hubs", "%"),
}
DEFINITIONS = {
    "base": "Live companies whose primary SSIC matches the segment, placed by registered postal code.",
    "addressable": "Base minus home-based (HDB residential), SSIC 70 head offices, companies under 1 year old and "
                   "late annual-return filers. ACRA has no headcount, so the ICP's 10-200 employees is not applied.",
    "density": "Base divided by the planning area's land area (URA).",
    "growth": f"Registrations in the last 12 months (to the ACRA data date) over the 12 months before, minus 1, "
              f"counting companies still live. Shown only when the prior 12 months have at least {MIN_GROWTH_BASE}.",
    "age": "Median years since registration.",
    "ontime": "Share of annual-return filers that filed within 13 months.",
    "accounts": "Our accounts in the segment at stage contacted or later (scoped to the viewer).",
    "customers": "Our accounts at stage handed_over (won).",
    "penetration": "Customers divided by addressable. Not market share: there is no competitor data.",
    "coverage": "Our accounts divided by addressable.",
    "whitespace": "Addressable minus our accounts.",
    "hubs": f"Share of the base registered at a postal code with {HUB}+ live companies (corporate secretaries, "
            "serviced offices): the registered address is not where these companies operate.",
}
PCT = {"growth", "ontime", "penetration", "coverage", "hubs"}
NOUNS = {"clinics": "clinic companies", "fnb": "F&B companies", "retail": "retail companies",
         "logistics": "logistics companies", "professional_services": "professional-services firms",
         "education": "education companies"}


# ----------------------------------------------------------------------------
# Geography
# ----------------------------------------------------------------------------
class Geo:
    def __init__(self, root: Path):
        self.fc = json.loads((root / GEO / "sg_planning_areas.geojson").read_text())
        self.geo = json.loads((root / GEO / "sg_postal_geo.json").read_text())
        self.meta = mc.load_yaml(root / GEO / "sg_geo.meta.yaml", {}) or {}
        self.areas = [f["properties"] for f in self.fc["features"]]
        self.index = {a["id"]: i for i, a in enumerate(self.areas)}
        if [a["id"] for a in self.areas] != self.geo["areas"]:
            raise SystemExit("knowledge/geo is out of step: run `python3 scripts/build_geo.py build`")
        self.regions = {}
        for a in self.areas:
            self.regions.setdefault(a["region"], {"id": a["region"], "name": a["region_name"], "areas": []})
            self.regions[a["region"]]["areas"].append(a["id"])

    def place(self, postal: str) -> tuple[list[tuple[int, float]], str]:
        """[(area index, weight)] and the method: exact | prefix | sector | none."""
        code = re.sub(r"\D", "", str(postal or "")).zfill(6)
        if code in self.geo["exact"]:
            return [(self.geo["exact"][code], 1.0)], "exact"
        for key, table in ((code[:3], "prefixes"), (code[:2], "sectors")):
            hit = self.geo[table].get(key)
            if hit:
                return [(self.index[a], w) for a, w in hit["w"]], ("prefix" if table == "prefixes" else "sector")
        return [], "none"

    def find(self, query: str) -> tuple[str, list[str]] | None:
        """An area or region by id, name or a close spelling: ('area'|'region', [area ids])."""
        q = re.sub(r"[^a-z0-9]+", "-", (query or "").lower()).strip("-")
        q = {"amk": "ang-mo-kio", "cbd": "downtown-core", "ne": "north-east", "northeast": "north-east"}.get(q, q)
        q2 = re.sub(r"-region$", "", q)
        if q2 in self.regions:
            return "region", list(self.regions[q2]["areas"])
        if q in self.index:
            return "area", [q]
        cands = [a["id"] for a in self.areas if a["id"].replace("-", "") == q.replace("-", "")]
        if not cands:
            cands = [a["id"] for a in self.areas if a["id"].startswith(q) or q in a["id"]]
        return ("area", cands[:1]) if len(cands) == 1 else None

    def licence(self, date: str) -> str:
        return " ".join(str(self.meta.get("licence", "")).split()).format(date=date)


# ----------------------------------------------------------------------------
# Accumulate a segment over the 55 areas
# ----------------------------------------------------------------------------
def largest_remainder(values: list[float], total: int) -> list[int]:
    floors = [math.floor(v) for v in values]
    left = total - sum(floors)
    order = sorted(range(len(values)), key=lambda i: (-(values[i] - floors[i]), i))
    for i in order[:max(0, left)]:
        floors[i] += 1
    return floors


def wmedian(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    pairs = sorted(pairs)
    half, acc = sum(w for _, w in pairs) / 2, 0.0
    for v, w in pairs:
        acc += w
        if acc >= half:
            return v
    return pairs[-1][0]


def scope(root: Path, owner: str) -> tuple[str, str]:
    """(label, owner filter) for 'our accounts'; a rep can never see the team (rule 16)."""
    me = mc.current_user(root) or {}
    if owner in ("me", "", None):
        return "my accounts", me.get("id", "")
    if owner == "team":
        if me.get("role") != "manager":
            raise SystemExit("Only the manager can see the team's accounts on the map; use --owner me.")
        return "team accounts", "*"
    if owner != me.get("id") and me.get("role") != "manager":
        raise SystemExit("A rep can see only their own accounts; use --owner me.")
    return f"{owner}'s accounts", owner


def our_accounts(root: Path, who: str) -> dict[str, dict]:
    out = {}
    for page in mc.iter_pages("account", root):
        m = page.meta or {}
        if mc.norm(m.get("market")).upper() != "SG" or not m.get("reg_id"):
            continue
        if who != "*" and mc.norm(m.get("owner")) != who:
            continue
        out[mc.norm(m["reg_id"]).upper()] = {"id": mc.norm(m.get("id")) or page.path.stem, "name": mc.norm(m.get("name")),
                                             "stage": mc.norm(m.get("stage")), "owner": mc.norm(m.get("owner"))}
    return out


class Market:
    def __init__(self, ctx: ca.Ctx, geo: Geo, rows: list[dict], accounts: dict[str, dict], exclude_hubs: bool):
        self.ctx, self.geo = ctx, geo
        n = len(geo.areas)
        z = lambda: [0.0] * n  # noqa: E731
        self.base, self.addr, self.new12, self.prev12, self.est = z(), z(), z(), z(), z()
        self.filers, self.ontime, self.acc, self.cust, self.hub = z(), z(), z(), z(), z()
        self.ages: list[list] = [[] for _ in range(n)]
        self.years: list[dict] = [{} for _ in range(n)]
        self.methods = {"exact": 0, "prefix": 0, "sector": 0, "none": 0}
        self.pins: list[dict] = []
        self.hub_codes = {p for (p,) in ctx.con.execute(
            "SELECT postal FROM live WHERE postal != '' GROUP BY postal HAVING COUNT(*) >= ?", (HUB,))}
        self.excluded_hubs = 0
        y1 = ctx.as_of - dt.timedelta(days=365)
        y2 = ctx.as_of - dt.timedelta(days=730)
        for r in rows:
            at_hub = r.get("postal") in self.hub_codes
            if exclude_hubs and at_hub:
                self.excluded_hubs += 1
                continue
            weights, how = geo.place(r.get("postal"))
            self.methods[how] += 1
            if not weights:
                continue
            reg = mc.to_date(r.get("reg_date"))
            age = ca.age_years(ctx, r)
            filing = ca.files_on_time(ctx, r)
            addressable = (not ca.is_home(ctx, r) and not str(r.get("ssic") or "").startswith("70")
                           and age is not None and age >= 1 and filing is not False)
            acct = accounts.get(str(r["uen"]).upper())
            for i, w in weights:
                self.base[i] += w
                if how != "exact":
                    self.est[i] += w
                if at_hub:
                    self.hub[i] += w
                if addressable:
                    self.addr[i] += w
                if reg and reg > y1:
                    self.new12[i] += w
                elif reg and reg > y2:
                    self.prev12[i] += w
                if reg:
                    self.years[i][reg.year] = self.years[i].get(reg.year, 0.0) + w
                if age is not None:
                    self.ages[i].append((age, w))
                if filing is not None:
                    self.filers[i] += w
                    self.ontime[i] += w if filing else 0
                if acct and acct["stage"] in TOUCHED:
                    self.acc[i] += w
                    if acct["stage"] in CUSTOMER:
                        self.cust[i] += w
            if acct:
                top = max(weights, key=lambda iw: iw[1])[0]
                self.pins.append({"account": acct["id"], "name": acct["name"], "stage": acct["stage"],
                                  "area": geo.areas[top]["id"], "approx": how != "exact"})
        self.segment_total = len(rows) - self.excluded_hubs
        self.placed = self.segment_total - self.methods["none"]
        self.int_base = largest_remainder(self.base, self.placed)
        self.int_addr = largest_remainder(self.addr, round(sum(self.addr)))
        self.int_acc = largest_remainder(self.acc, round(sum(self.acc)))
        self.int_cust = largest_remainder(self.cust, round(sum(self.cust)))

    def values(self, i: int) -> dict:
        b, a = self.int_base[i], self.int_addr[i]
        few = b < MIN_AREA
        area_km2 = self.geo.areas[i]["area_km2"] or 0
        growth = (self.new12[i] / self.prev12[i] - 1) if self.prev12[i] >= MIN_GROWTH_BASE else None
        med = wmedian(self.ages[i])
        return {"base": b, "addressable": a,
                "density": round(b / area_km2, 1) if area_km2 >= 0.05 else None,
                "growth": None if few or growth is None else round(100 * growth, 1),
                "age": None if few or med is None else round(med, 1),
                "ontime": None if few or self.filers[i] < MIN_AREA else round(100 * self.ontime[i] / self.filers[i], 1),
                "accounts": self.int_acc[i], "customers": self.int_cust[i],
                "penetration": round(100 * self.int_cust[i] / a, 2) if a else None,
                "coverage": round(100 * self.int_acc[i] / a, 2) if a else None,
                "whitespace": max(0, a - self.int_acc[i]),
                "hubs": round(100 * self.hub[i] / self.base[i], 1) if self.base[i] and not few else None}

    def total(self, idx: list[int] | None = None) -> dict:
        whole = idx is None
        idx = list(range(len(self.geo.areas))) if idx is None else idx
        s = lambda xs: sum(xs[i] for i in idx)  # noqa: E731
        b, a = sum(self.int_base[i] for i in idx), sum(self.int_addr[i] for i in idx)
        unplaced = self.segment_total - self.placed if whole else 0
        b += unplaced
        acc, cust = sum(self.int_acc[i] for i in idx), sum(self.int_cust[i] for i in idx)
        prev = s(self.prev12)
        med = wmedian([p for i in idx for p in self.ages[i]])
        land = sum(self.geo.areas[i]["area_km2"] for i in idx)
        return {"base": b, "addressable": a, "density": round(b / land, 1) if land else None,
                "growth": round(100 * (s(self.new12) / prev - 1), 1) if prev >= MIN_GROWTH_BASE else None,
                "age": round(med, 1) if med is not None else None,
                "ontime": round(100 * s(self.ontime) / s(self.filers), 1) if s(self.filers) else None,
                "accounts": acc, "customers": cust,
                "penetration": round(100 * cust / a, 2) if a else None,
                "coverage": round(100 * acc / a, 2) if a else None,
                "whitespace": max(0, a - acc), "hubs": round(100 * s(self.hub) / s(self.base), 1) if s(self.base) else None,
                "approx_pct": round(100 * s(self.est) / s(self.base), 1) if s(self.base) else 0.0, "unplaced": unplaced}

    def by_year(self, idx: list[int], years: int = 10) -> list[dict]:
        last = self.ctx.as_of.year
        out = []
        for y in range(last - years + 1, last + 1):
            out.append({"label": str(y), "value": round(sum(self.years[i].get(y, 0.0) for i in idx))})
        return out


# ----------------------------------------------------------------------------
# Scene and sections
# ----------------------------------------------------------------------------
def fmt(key: str, v) -> str:
    if v is None:
        return "too few to tell"
    if key in PCT:
        return f"{v:g}%"
    unit = MEASURES[key][1]
    if isinstance(v, float):
        return f"{v:,.1f} {unit}" if unit in ("yrs", "per km²") else f"{v:,.1f}"
    return f"{v:,}"


def breaks(vals: list[float], k: int = 5) -> list[float]:
    """k stepped classes by quantile: k-1 rounded break points (deterministic)."""
    v = sorted(x for x in vals if x is not None)
    if len(v) < k:
        return sorted(set(v))[:k - 1]
    out = []
    for j in range(1, k):
        x = v[min(len(v) - 1, int(len(v) * j / k))]
        mag = 10 ** max(0, int(math.log10(abs(x))) - 1) if x else 1
        out.append(round(x / mag) * mag if abs(x) >= 10 else round(x, 1))
    return sorted(set(out))


def measure(key: str) -> dict:
    label, unit = MEASURES[key]
    return {"key": key, "label": label, "unit": unit}


def scene(mk: Market, seg: dict, height: str, colour: str, focus: list[str], camera: str, halos: list[str],
          pins: bool = True) -> dict:
    vals = [mk.values(i) for i in range(len(mk.geo.areas))]
    areas = []
    for i, a in enumerate(mk.geo.areas):
        approx = mk.base[i] > 0 and mk.est[i] / mk.base[i] > 0.1
        areas.append({"id": a["id"], "name": a["name"], "region": a["region"], "area_km2": a["area_km2"],
                      "values": vals[i], "approx": approx})
    diverging = colour in ("growth",)
    tot = mk.total()
    return ca.section(
        "map3d", seg["title"], refs=["knowledge/geo/sg_geo.meta.yaml", "docs/Sales-Mama-3D-Insights-design-spec.md"],
        segment=seg["id"], height=measure(height),
        colour={**measure(colour), "breaks": breaks([v[colour] for v in vals]),
                "scheme": "mama-div" if diverging else "mama-seq"},
        areas=areas, regions=[{"id": r["id"], "name": r["name"]} for r in mk.geo.regions.values()],
        focus=focus, camera=camera, halos=halos,
        accounts=mk.pins if pins else [],
        method={"placement": {k: v for k, v in mk.methods.items()}, "approx_pct": tot["approx_pct"],
                "excluded_hubs": mk.excluded_hubs, "definitions": {k: DEFINITIONS[k] for k in {height, colour,
                                                                                            "base", "addressable", "penetration"}},
                "note": "Registered address, not where a company operates. ≈ marks area counts estimated from the postal "
                        "sector; totals are exact."})


def headline(mk: Market, t: dict, who: str, title: str) -> dict:
    items = [
        {"key": "base", "label": "Live companies", "value": t["base"], "status": "neutral",
         **({"note": f"{t['unplaced']:,} without a usable postal code are not on the map"} if t.get("unplaced") else {})},
        {"key": "addressable", "label": "Addressable", "value": t["addressable"], "status": "neutral",
         "note": "not home-based, 1 yr+, filing on time"},
        {"key": "growth", "label": "New registrations vs prior year", "value": t["growth"], "unit": "%",
         "status": "neutral" if t["growth"] is None else ("good" if t["growth"] >= 0 else "warn")},
        {"key": "age", "label": "Median age", "value": t["age"], "unit": "yrs", "status": "neutral"},
        {"key": "accounts", "label": f"Our accounts ({who})", "value": t["accounts"], "status": "neutral"},
        {"key": "penetration", "label": "Penetration", "value": t["penetration"], "unit": "%", "status": "neutral",
         "note": "customers ÷ addressable; not market share"},
        {"key": "whitespace", "label": "Whitespace", "value": t["whitespace"], "status": "neutral"},
    ]
    return ca.section("metrics", title, subtitle=f"ACRA data as of {mk.ctx.as_of} · {t['approx_pct']}% of placements "
                                                 f"estimated (≈)", items=items)


def segment_of(ctx: ca.Ctx, args) -> tuple[dict, list[dict]]:
    ns = SimpleNamespace(industry=args.segment, ssic=args.ssic, district=None, name=None, type=None)
    where, params, label = ca.segment_filter(ctx, ns)
    rows = ca.rows_where(ctx, where, params)
    sid = args.segment or (f"ssic-{args.ssic}" if args.ssic else "all")
    noun = NOUNS.get(args.segment or "", label + " companies") if args.segment else \
        ("live companies" if label == "all live companies" else label + " companies")
    return {"id": sid, "label": label, "noun": noun, "title": f"Singapore market: {noun}"}, rows


def area_rows(mk: Market, key: str, idx: list[int] | None = None) -> list[dict]:
    idx = list(range(len(mk.geo.areas))) if idx is None else idx
    out = []
    for i in idx:
        v = mk.values(i)
        a = mk.geo.areas[i]
        out.append({"area": a["name"] + (" ≈" if mk.base[i] and mk.est[i] / mk.base[i] > 0.1 else ""),
                    "region": a["region_name"], "base": v["base"], key: v[key], "_id": a["id"], "_v": v[key]})
    return out


def ranked(mk: Market, key: str) -> list[int]:
    vals = [(mk.values(i)[key], i) for i in range(len(mk.geo.areas))]
    return [i for v, i in sorted((x for x in vals if x[0] is not None), key=lambda x: (-x[0], mk.geo.areas[x[1]]["id"]))]


def next_prompts(seg: dict, area: str | None = None) -> list[dict]:
    s = seg["id"] if seg["id"] != "all" else ""
    flag = f" --segment {s}" if s and not s.startswith("ssic-") else ""
    out = [{"label": "Where is the whitespace?", "prompt": f"Where is the whitespace for {seg['noun']} on the map?"},
           {"label": "Fastest growing areas", "prompt": f"Which areas are growing fastest for {seg['noun']}?"}]
    if area:
        out.insert(0, {"label": f"Compare {area} with its region", "prompt": f"Compare {area} with the rest of its region{flag}"})
    else:
        out.insert(0, {"label": "Biggest areas", "prompt": f"Which planning areas have the most {seg['noun']}?"})
    return out


# ----------------------------------------------------------------------------
# Questions
# ----------------------------------------------------------------------------
def q_overview(mk: Market, seg: dict, who: str, args) -> dict:
    t = mk.total()
    order = ranked(mk, "base")
    top = order[:5]
    regions = []
    for r in mk.geo.regions.values():
        idx = [mk.geo.index[a] for a in r["areas"]]
        regions.append({"label": r["name"], "value": sum(mk.int_base[i] for i in idx)})
    regions.sort(key=lambda x: -x["value"])
    halos = [mk.geo.areas[i]["id"] for i in ranked(mk, "whitespace")[:5]]
    parts = [
        ("overview", headline(mk, t, who, seg["title"])),
        ("map", scene(mk, seg, args.height or "base", args.colour or "growth", [], "island", halos)),
        ("regions", ca.series("By region", "category", regions, share_of_total=True)),
        ("top", ca.rows_section("Biggest planning areas", [("area", "Area"), ("region", "Region"),
                                                           ("base", "Live companies", True), ("growth", "Growth 12m %", True)],
                                [{k: x[k] for k in ("area", "region", "base")} | {"growth": mk.values(x_i)["growth"]}
                                 for x, x_i in ((area_rows(mk, "base", [i])[0], i) for i in order[:10])],
                                next=next_prompts(seg))),
        ("trend", ca.series("New registrations per year", "time", mk.by_year(list(range(len(mk.geo.areas)))))),
    ]
    big = regions[0]
    lead = mk.geo.areas[top[0]]["name"] if top else "-"
    summary = [f"Singapore has {t['base']:,} {seg['noun']}; the {big['label']} region holds the most ({big['value']:,}).",
               f"The biggest planning area is {lead} with {mk.int_base[top[0]]:,}." if top else "",
               f"{t['addressable']:,} are addressable; we work {t['accounts']:,} of them, penetration "
               f"{fmt('penetration', t['penetration'])}." if t["addressable"] else ""]
    if mk.excluded_hubs:
        summary.append(f"Leaving out {mk.excluded_hubs:,} registered at {HUB}+-company postal codes (registration hubs).")
    return ca.spec_of(seg["title"], [s for s in summary if s], parts)


def q_area(mk: Market, seg: dict, who: str, args) -> dict:
    hit = mk.geo.find(args.area)
    if not hit:
        names = ", ".join(a["name"] for a in mk.geo.areas[:8])
        raise SystemExit(f"no planning area or region matches “{args.area}” (e.g. {names}, or east / west / central)")
    kind, ids = hit
    idx = [mk.geo.index[a] for a in ids]
    t = mk.total(idx)
    name = mk.geo.regions[mk.geo.areas[idx[0]]["region"]]["name"] + " region" if kind == "region" else mk.geo.areas[idx[0]]["name"]
    title = f"{name}: {seg['noun']}"
    order = ranked(mk, "base")
    parts = [("overview", headline(mk, t, who, title)),
             ("map", scene(mk, seg, args.height or "base", args.colour or "growth", ids, "frame-focus",
                           [a for a in ids if mk.values(mk.geo.index[a])["whitespace"] > 0][:5])),
             ("trend", ca.series(f"New registrations per year, {name}", "time", mk.by_year(idx)))]
    if kind == "region":
        rows = sorted(area_rows(mk, "growth", idx), key=lambda r: -r["base"])
        parts.append(("areas", ca.rows_section(f"Planning areas in the {name}", [("area", "Area"), ("base", "Live companies", True),
                                                                                ("growth", "Growth 12m %", True)],
                                               [{k: r[k] for k in ("area", "base", "growth")} for r in rows],
                                               next=next_prompts(seg, name))))
        summary = [f"The {name} has {t['base']:,} {seg['noun']} across {len(idx)} planning areas.",
                   f"New registrations vs the year before: {fmt('growth', t['growth'])}; median age {fmt('age', t['age'])}."]
    else:
        i = idx[0]
        rank = order.index(i) + 1 if i in order else None
        approx = mk.base[i] and mk.est[i] / mk.base[i] > 0.1
        parts.append(("rank", ca.section("metrics", f"{name} among 55 planning areas", items=[
            {"key": "rank", "label": "Rank by size", "value": rank, "unit": f"of {len(order)}", "status": "neutral"},
            {"key": "density", "label": "Companies per km²", "value": mk.values(i)["density"], "status": "neutral"},
            {"key": "hubs", "label": "At registration hubs", "value": mk.values(i)["hubs"], "unit": "%", "status": "neutral"}],
            next=next_prompts(seg, name))))
        summary = [f"{name} has {'about ' if approx else ''}{t['base']:,} {seg['noun']}, rank {rank} of {len(order)}.",
                   f"New registrations vs the year before: {fmt('growth', t['growth'])}; whitespace {t['whitespace']:,}."]
    return ca.spec_of(title, summary, parts)


def q_rank(mk: Market, seg: dict, who: str, args) -> dict:
    key = args.by
    order = ranked(mk, key)[: args.top]
    ids = [mk.geo.areas[i]["id"] for i in order]
    rows = area_rows(mk, key, order)
    label = MEASURES[key][0]
    halos = ids[:5] if key == "whitespace" else []
    parts = [("map", scene(mk, seg, args.height or ("base" if key in ("growth", "penetration", "coverage", "age", "ontime") else key),
                           args.colour or key, ids[:5], "frame-focus", halos)),
             ("ranking", ca.rows_section(f"Top {len(rows)} planning areas by {label.lower()}",
                                         [("area", "Area"), ("region", "Region"), ("base", "Live companies", True),
                                          (key, label, True)],
                                         [{k: r[k] for k in ("area", "region", "base", key)} for r in rows],
                                         next=next_prompts(seg)))]
    if not rows:
        return ca.spec_of(f"{seg['title']} by {label.lower()}", [f"Too few {seg['noun']} to rank by {label.lower()}."], parts)
    first = rows[0]
    summary = [f"{first['area'].rstrip(' ≈')} leads on {label.lower()}: {fmt(key, first[key])}"
               + (f", from {first['base']:,} {seg['noun']}." if key != "base" else ".")]
    if len(rows) > 1:
        summary.append(f"Next: {rows[1]['area'].rstrip(' ≈')} ({fmt(key, rows[1][key])})"
                       + (f" and {rows[2]['area'].rstrip(' ≈')} ({fmt(key, rows[2][key])})." if len(rows) > 2 else "."))
    if key == "growth":
        summary.append(f"Growth is shown only where the prior 12 months had {MIN_GROWTH_BASE}+ registrations.")
    return ca.spec_of(f"{seg['title']} by {label.lower()}", summary, parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Singapore market questions as data for the 3D Insights scene.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("overview", help="the whole island: regions, biggest areas, headline metrics")
    a = sub.add_parser("area", help="one planning area or region")
    a.add_argument("--area", required=True, help="planning area or region, e.g. tampines, 'jurong east', east")
    r = sub.add_parser("rank", help="planning areas ranked by a measure")
    r.add_argument("--by", choices=[k for k in MEASURES if k != "customers"], default="base")
    r.add_argument("--top", type=int, default=10)
    for p in (o, a, r):
        p.add_argument("--segment", help="ICP industry (knowledge/icp.md), e.g. clinics")
        p.add_argument("--ssic", help="SSIC code prefix, e.g. 86")
        p.add_argument("--owner", default="me", help="me (default) | team (manager only) | <rep id>")
        p.add_argument("--height", choices=list(MEASURES), help="measure for tower height")
        p.add_argument("--colour", choices=list(MEASURES), help="measure for tower colour")
        p.add_argument("--exclude-hubs", action="store_true", help=f"leave out postal codes with {HUB}+ registrations")
        p.add_argument("--json", action="store_true", help="print JSON (the default)")
        p.add_argument("--out", help="also save the data (e.g. company-check/reports/map-<slug>.json)")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    if not (root / "company-check" / "data" / "registry.sqlite").is_file():
        print("No registry index: run `python3 scripts/registry_data.py refresh` first (company-check/README.md).")
        return 1
    ctx = ca.Ctx(root)
    geo = Geo(root)
    who, owner = scope(root, args.owner)
    seg, rows = segment_of(ctx, args)
    mk = Market(ctx, geo, rows, our_accounts(root, owner) if owner else {}, args.exclude_hubs)
    spec = {"overview": q_overview, "area": q_area, "rank": q_rank}[args.cmd](mk, seg, who, args)
    spec["as_of"] = ctx.as_of.isoformat()
    spec["licence"] = ctx.licence() + " " + geo.licence(geo.geo.get("data_date", ""))
    if args.out:
        p = Path(args.out)
        p = p if p.is_absolute() else root / p
        p.parent.mkdir(parents=True, exist_ok=True)
        mc.write_text(p, json.dumps(spec, indent=2, ensure_ascii=False, default=str) + "\n")
        spec["data"] = mc.rel_posix(p, root)
    print(json.dumps(spec, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
