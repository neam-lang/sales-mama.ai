"""Lead scoring for Sales Mama (PLAN.md §8, ADR-0003).

For each account: fit (its market's section of icp.md), intent (cited
`## Signals` bullets: weight x source trust x decay), propensity (CRM prior)
and engagement (log/touches.csv), weighted by knowledge/scoring.yaml.
Writes `score`, `tier`, `score_parts`, `score_updated` (only when they
change) and adds `hot` to `risk` when the score jumps by hot_alert.score_jump.
Never touches owner, stage, updated or the page body.

Uncited signal bullets (no existing raw/ file) are ignored and reported (rule 3).

    python3 scripts/score.py                  # manager: every account
    python3 scripts/score.py --id acme-trading
    python3 scripts/score.py --dry-run --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402

RAW_LINK_RE = re.compile(r"\]\((raw/[^)\s]+)\)")
DATE_RE = re.compile(r"\((\d{4}-\d{2}-\d{2})\)")
DEFAULTS = {
    "weights": {"fit": 0.35, "intent": 0.40, "propensity": 0.15, "engagement": 0.10},
    "fit": {"industry_match": 0.4, "size_in_range": 0.3, "region_match": 0.1, "owns_prerequisite": 0.2,
            "unknown": 0.5},
    "trust": {"crm": 1.0, "research": 0.8, "default": 0.5},
    "engagement": {"replied": 0.6, "meeting": 1.0, "no_reply_after_3": -0.3},
    "tiers": {"A": 0.70, "B": 0.45},
    "hot_jump": 0.20,
}


@dataclass
class Signal:
    term: str
    date: object          # dt.date | None
    evidence: str
    source: str           # raw/... path
    line: str


# Knowledge --------------------------------------------------------------------
class Knowledge:
    def __init__(self, root: Path):
        self.root = root
        cfg = mc.load_yaml(root / "knowledge" / "scoring.yaml", {}) or {}
        self.weights = {**DEFAULTS["weights"], **(cfg.get("weights") or {})}
        self.fit = {**DEFAULTS["fit"], **(cfg.get("fit") or {})}
        intent = cfg.get("intent") or {}
        self.trust = {**DEFAULTS["trust"], **(intent.get("trust") or {})}
        self.eng = {**DEFAULTS["engagement"], **(cfg.get("engagement") or {})}
        self.tiers = {**DEFAULTS["tiers"], **(cfg.get("tiers") or {})}
        self.hot_jump = float((cfg.get("hot_alert") or {}).get("score_jump", DEFAULTS["hot_jump"]))
        self.prop_missing = float((cfg.get("propensity") or {}).get("missing", 0.0))
        onto = mc.load_yaml(root / "knowledge" / "ontology.yaml", {}) or {}
        self.signals = onto.get("signals") or {}
        self.icp = mc.load_icp(root)
        src = mc.load_yaml(root / "knowledge" / "sources.yaml", {}) or {}
        self.source_trust = {mc.norm(s.get("id")): float(s.get("trust", self.trust["default"]))
                             for s in (src.get("sources") or []) if isinstance(s, dict) and s.get("id")}
        self.products = []
        folder = root / "knowledge" / "products"
        for p in sorted(folder.glob("*.y*ml")) if folder.is_dir() else []:
            data = mc.load_yaml(p, {})
            if isinstance(data, dict):
                data.setdefault("id", p.stem)
                self.products.append(data)


# Signals ----------------------------------------------------------------------
def parse_signals(page: mc.Page, root: Path) -> tuple[list[Signal], list[str]]:
    """Cited signal bullets from `## Signals`, and the uncited / unknown ones."""
    good, bad = [], []
    for line in mc.section(page.body, "Signals").splitlines():
        s = line.strip()
        if not re.match(r"^[-*+]\s+", s):
            continue
        content = re.sub(r"^[-*+]\s+", "", s).strip()
        term = re.split(r"[\s—:]", content, maxsplit=1)[0].strip().strip("`")
        links = RAW_LINK_RE.findall(content)
        if not links or not all((root / u.split("#")[0]).exists() for u in links):
            bad.append(content)
            continue
        dates = DATE_RE.findall(content.split("](")[0])
        parts = [x.strip() for x in content.split("—")]
        evidence = parts[1] if len(parts) > 2 else ""
        evidence = DATE_RE.sub("", evidence).strip()
        good.append(Signal(term, mc.to_date(dates[-1]) if dates else None, evidence, links[0].split("#")[0], content))
    return good, bad


def trust_for(source: str, kn: Knowledge) -> float:
    parts = source.split("/")
    if len(parts) >= 4 and parts[1] == "signals":
        return kn.source_trust.get(parts[3], kn.trust["default"])
    if len(parts) >= 2 and parts[1] in ("crm", "research"):
        return float(kn.trust[parts[1]])
    return float(kn.trust["default"])


def strength(sig: Signal, kn: Knowledge, on) -> float:
    """weight x trust x 0.5^(age / half-life); half-life = decay_days / 2."""
    spec = kn.signals.get(sig.term) or {}
    weight = float(spec.get("weight", 0))
    decay_days = float(spec.get("decay_days", 60)) or 60
    age = max(0, (on - sig.date).days) if sig.date else decay_days
    return weight * trust_for(sig.source, kn) * 0.5 ** (age / (decay_days / 2))


def usable(sig: Signal, market: str, kn: Knowledge) -> bool:
    spec = kn.signals.get(sig.term)
    if not isinstance(spec, dict):
        return False
    markets = mc.as_list(spec.get("markets"))
    return not markets or market in markets


# Parts ------------------------------------------------------------------------
def to_int(value) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def fit_part(meta: dict, kn: Knowledge) -> tuple[float, list[str]]:
    market = mc.norm(meta.get("market")).upper()
    fit = kn.icp["fit"].get(market) or {}
    excl = kn.icp.get("exclude") or {}
    w, unk = kn.fit, float(kn.fit["unknown"])
    notes: list[str] = []
    name = mc.norm(meta.get("name")).lower()
    for pat in mc.as_list(excl.get("name_patterns")):
        if re.search(str(pat), name, re.I):
            return 0.0, [f"excluded name pattern `{pat}`"]
    emp = to_int(meta.get("employees"))
    if emp is not None and excl.get("max_employees") and emp > int(excl["max_employees"]):
        return 0.0, ["large enterprise"]
    total = 0.0
    industry = mc.norm(meta.get("industry"))
    if not industry:
        total += w["industry_match"] * unk
        notes.append("industry unknown")
    elif industry in [str(x) for x in mc.as_list(fit.get("industries"))]:
        total += w["industry_match"]
    else:
        notes.append(f"industry {industry} not in ICP")
    band = mc.as_list(fit.get("employees"))
    if emp is None or len(band) != 2:
        total += w["size_in_range"] * unk
        notes.append("size unknown")
    elif int(band[0]) <= emp <= int(band[1]):
        total += w["size_in_range"]
    else:
        notes.append(f"{emp} staff outside {band[0]}–{band[1]}")
    regions = [str(r).lower() for r in mc.as_list(fit.get("regions"))]
    place = " ".join(mc.norm(meta.get(k)).lower() for k in ("city", "region")).strip()
    if not regions:
        total += w["region_match"]
    elif not place:
        total += w["region_match"] * unk
        notes.append("region unknown")
    elif any(r in place for r in regions):
        total += w["region_match"]
    else:
        notes.append("region outside ICP")
    owned = {str(x) for x in mc.as_list(meta.get("products_owned"))}
    prereqs = {str(r) for p in kn.products if market in [str(m) for m in mc.as_list(p.get("available_in"))]
               for r in mc.as_list(p.get("requires"))}
    if not prereqs or owned & prereqs:
        total += w["owns_prerequisite"]
    else:
        notes.append("no prerequisite owned")
    return min(1.0, total), notes


def intent_part(signals: list[Signal], market: str, kn: Knowledge, on) -> float:
    best: dict[str, float] = {}
    for sig in signals:
        if not usable(sig, market, kn):
            continue
        st = strength(sig, kn, on)
        if (kn.signals[sig.term] or {}).get("negative") or st < 0:
            best[sig.term] = min(best.get(sig.term, 0.0), st)
        else:
            best[sig.term] = max(best.get(sig.term, 0.0), st)
    return max(0.0, min(1.0, sum(best.values())))


def propensity_part(meta: dict, kn: Knowledge) -> float:
    try:
        v = float(meta.get("propensity"))
    except (TypeError, ValueError):
        return kn.prop_missing
    return max(0.0, min(1.0, v))


def engagement_part(account: str, touches: list[dict], kn: Knowledge) -> float:
    rows = [t for t in touches if mc.link_id(t.get("account")) == account]
    statuses = {mc.norm(t.get("status")) for t in rows}
    if statuses & {"meeting_booked", "meeting_held"}:
        return float(kn.eng["meeting"])
    if "replied" in statuses:
        return float(kn.eng["replied"])
    if sum(1 for t in rows if mc.norm(t.get("status")) == "sent") >= 3:
        return float(kn.eng["no_reply_after_3"])
    return 0.0


def tier_for(score: float, kn: Knowledge) -> str:
    if score >= float(kn.tiers["A"]):
        return "A"
    if score >= float(kn.tiers["B"]):
        return "B"
    return "C"


def score_page(page: mc.Page, kn: Knowledge, touches: list[dict], on) -> dict:
    meta = page.meta
    market = mc.norm(meta.get("market")).upper()
    signals, uncited = parse_signals(page, kn.root)
    fit, notes = fit_part(meta, kn)
    parts = {
        "fit": round(fit, 2),
        "intent": round(intent_part(signals, market, kn, on), 2),
        "propensity": round(propensity_part(meta, kn), 2),
        "engagement": round(engagement_part(page.id, touches, kn), 2),
    }
    score = sum(float(kn.weights.get(k, 0)) * v for k, v in parts.items())
    score = round(max(0.0, min(1.0, score)), 2)
    return {"id": page.id, "path": page.rel, "score": score, "tier": tier_for(score, kn), "score_parts": parts,
            "notes": notes, "uncited": uncited}


# Main -------------------------------------------------------------------------
def select_pages(root: Path, ids: list[str], user: dict | None) -> tuple[list[mc.Page], str]:
    pages = list(mc.iter_pages("account", root))
    manager = bool(user) and mc.norm(user.get("role")) == "manager"
    if ids:
        by_id = {p.id: p for p in pages}
        missing = [i for i in ids if i not in by_id]
        if missing:
            return [], f"No account page for: {', '.join(missing)}"
        pages = [by_id[i] for i in ids]
    if not manager:
        me = mc.norm((user or {}).get("id"))
        if ids:
            others = [p.id for p in pages if mc.norm(p.meta.get("owner")) != me or not me]
            if others:
                return [], f"Refused: you don't own {', '.join(others)} (rules 6, 16)."
        pages = [p for p in pages if me and mc.norm(p.meta.get("owner")) == me]
    return pages, ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Score accounts from knowledge/scoring.yaml (fit, intent, "
                                             "propensity, engagement) and write score, tier, score_parts.")
    ap.add_argument("--id", action="append", default=[], help="account id (repeatable); default: all you may score")
    ap.add_argument("--dry-run", action="store_true", help="compute and print; write nothing")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    user = mc.current_user(root)
    pages, err = select_pages(root, args.id, user)
    if err:
        print(err)
        return 1
    kn = Knowledge(root)
    touches = mc.load_touches(root)
    on = mc.today()
    results, changed = [], 0
    for page in pages:
        r = score_page(page, kn, touches, on)
        old = page.meta
        try:
            old_score = float(old.get("score"))
        except (TypeError, ValueError):
            old_score = None
        r["previous"] = old_score
        r["hot"] = old_score is not None and r["score"] - old_score >= kn.hot_jump
        same = old_score == r["score"] and mc.norm(old.get("tier")) == r["tier"] \
            and (old.get("score_parts") or {}) == r["score_parts"]
        r["changed"] = not same
        if not same and not args.dry_run:
            changes = {"score": r["score"], "tier": r["tier"], "score_parts": r["score_parts"],
                       "score_updated": on.isoformat()}
            risk = [str(x) for x in mc.as_list(old.get("risk"))]
            if r["hot"] and "hot" not in risk:
                changes["risk"] = risk + ["hot"]
            mc.update_frontmatter(page.path, changes)
            changed += 1
        results.append(r)
    mix = {t: sum(1 for r in results if r["tier"] == t) for t in mc.TIERS}
    if not args.dry_run and results:
        mc.append_log("score", (user or {}).get("id", ""), f"{len(results)} accounts",
                      f"A {mix['A']} · B {mix['B']} · C {mix['C']}; {changed} changed", root)
    if args.json:
        print(json.dumps({"date": on.isoformat(), "dry_run": args.dry_run, "tiers": mix, "changed": changed,
                          "results": results}, indent=2, default=str))
        return 0
    for r in sorted(results, key=lambda x: (-x["score"], x["id"])):
        prev = "" if r["previous"] is None or not r["changed"] else f" (was {r['previous']:.2f})"
        flag = "  HOT" if r["hot"] else ""
        p = r["score_parts"]
        print(f"  {r['tier']}  {r['score']:.2f}{prev}  {r['id']:40}  fit {p['fit']:.2f} · intent {p['intent']:.2f}"
              f" · prop {p['propensity']:.2f} · eng {p['engagement']:.2f}{flag}")
        for u in r["uncited"]:
            print(f"      ignored uncited signal: {u[:70]}")
    print(f"{'DRY RUN — ' if args.dry_run else ''}{len(results)} accounts · tier A {mix['A']} · B {mix['B']} · "
          f"C {mix['C']} · {changed if not args.dry_run else sum(r['changed'] for r in results)} changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
