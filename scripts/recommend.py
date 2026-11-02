"""Product recommendation for one account (PLAN.md §6, ADR-0003). Read-only.

Walks signal -> pain -> product with knowledge/ontology.yaml and
knowledge/products/*.yaml:
- active signals: cited `## Signals` bullets (raw/ file exists) no older than
  the term's decay_days and allowed in the account's market; an active
  negative signal (e.g. layoffs_or_closure) means no recommendation now;
  hook signals imply no pain and are returned as `hooks`;
- products are excluded, in order, when not available in the market, already
  owned (skip_if_owned), missing a `requires` product, outside `fits`
  (industries, employees) or solving none of the active pains;
- rank = sum over matched pains of the strongest signal implying that pain
  (weight x trust x decay, as score.py); ties -> higher typical_value in the
  market, then id.

    python3 scripts/recommend.py harbourlight-foods
    python3 scripts/recommend.py harbourlight-foods --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402
import score as sc  # noqa: E402


def active_signals(page: mc.Page, kn: sc.Knowledge, on) -> tuple[list[sc.Signal], list[str]]:
    market = mc.norm(page.meta.get("market")).upper()
    signals, uncited = sc.parse_signals(page, kn.root)
    out, skipped = [], [f"uncited: {u[:60]}" for u in uncited]
    for sig in signals:
        if sig.term not in kn.signals:
            skipped.append(f"{sig.term}: not an ontology term")
        elif not sc.usable(sig, market, kn):
            skipped.append(f"{sig.term}: not used in {market}")
        elif sig.date is None:
            skipped.append(f"{sig.term}: no date")
        elif (on - sig.date).days > int((kn.signals[sig.term] or {}).get("decay_days", 60)):
            skipped.append(f"{sig.term} ({sig.date}): older than {kn.signals[sig.term].get('decay_days')} days")
        else:
            out.append(sig)
    return out, skipped


def recommend(root: Path, account: str, kn: sc.Knowledge | None = None, on=None) -> dict:
    kn = kn or sc.Knowledge(root)
    on = on or mc.today()
    path = root / "wiki" / "accounts" / f"{account}.md"
    page = mc.read_page(path, root) if path.is_file() else None
    if page is None or not page.meta:
        return {"account": account, "error": "no account page"}
    meta = page.meta
    market = mc.norm(meta.get("market")).upper()
    out = {"account": account, "market": market, "candidates": [], "excluded": [], "hooks": [],
           "skipped_signals": [], "reason": ""}
    if market not in mc.MARKETS:
        out["reason"] = "account has no market (rule 14)"
        return out
    signals, out["skipped_signals"] = active_signals(page, kn, on)
    negative = [s for s in signals if (kn.signals[s.term] or {}).get("negative")]
    if negative:
        n = negative[0]
        out["reason"] = f"negative signal: {n.term} ({n.date})"
        return out
    # pain -> strongest implying signal
    pains: dict[str, tuple[float, sc.Signal]] = {}
    for sig in signals:
        spec = kn.signals[sig.term] or {}
        implied = mc.as_list(spec.get("implies"))
        if spec.get("hook") and not implied:
            out["hooks"].append({"signal": sig.term, "date": str(sig.date), "evidence": sig.evidence,
                                 "source": sig.source})
        st = sc.strength(sig, kn, on)
        for pain in implied:
            if pain not in pains or st > pains[pain][0]:
                pains[pain] = (st, sig)
    if not signals:
        out["reason"] = "no active cited signals"
    elif not pains:
        out["reason"] = "active signals imply no pain (hooks only)"
    owned = {str(x) for x in mc.as_list(meta.get("products_owned"))}
    industry = mc.norm(meta.get("industry"))
    emp = sc.to_int(meta.get("employees"))
    for prod in kn.products:
        pid = mc.norm(prod.get("id"))
        why = ""
        fits = prod.get("fits") or {}
        band = mc.as_list(fits.get("employees"))
        inds = [str(x) for x in mc.as_list(fits.get("industries"))]
        req = [str(x) for x in mc.as_list(prod.get("requires"))]
        if market not in [str(m) for m in mc.as_list(prod.get("available_in"))]:
            why = f"not available in {market}"
        elif owned & {str(x) for x in mc.as_list(prod.get("skip_if_owned"))}:
            why = "already owned"
        elif req and not set(req) <= owned:
            why = f"requires {', '.join(sorted(set(req) - owned))}"
        elif inds and industry not in inds:
            why = f"industry {industry or 'unknown'} not in fits"
        elif emp is not None and len(band) == 2 and not int(band[0]) <= emp <= int(band[1]):
            why = f"{emp} staff outside {band[0]}–{band[1]}"
        matched = [p for p in mc.as_list(prod.get("solves")) if p in pains]
        if not why and not matched:
            why = "solves none of the active pains"
        if why:
            out["excluded"].append({"product": pid, "reason": why})
            continue
        value = (prod.get("typical_value") or {}).get(market)
        chain = [{"signal": pains[p][1].term, "date": str(pains[p][1].date), "evidence": pains[p][1].evidence,
                  "source": pains[p][1].source, "pain": p, "strength": round(pains[p][0], 3)} for p in matched]
        out["candidates"].append({"product": pid, "name": mc.norm(prod.get("name")),
                                  "score": round(sum(c["strength"] for c in chain), 3),
                                  "value": value, "currency": market_currency(root, market),
                                  "size_note": "" if emp is not None else "employees unknown", "chain": chain})
    out["candidates"].sort(key=lambda c: (-c["score"], -(c["value"] or 0), c["product"]))
    if not out["candidates"] and not out["reason"]:
        out["reason"] = "; ".join(f"{e['product']}: {e['reason']}" for e in out["excluded"])
    return out


def market_currency(root: Path, market: str) -> str:
    data = mc.load_yaml(root / "knowledge" / "markets.yaml", {}) or {}
    return mc.norm(((data.get("markets") or {}).get(market) or {}).get("currency"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Recommend products for one account: signal -> pain -> product, "
                                             "with exclusions (read-only).")
    ap.add_argument("account", help="account id (wiki/accounts/<id>.md)")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    r = recommend(root, mc.link_id(args.account))
    if args.json:
        print(json.dumps(r, indent=2, default=str))
        return 1 if r.get("error") else 0
    if r.get("error"):
        print(f"{args.account}: {r['error']}")
        return 1
    print(f"{r['account']} ({r['market']})")
    for i, c in enumerate(r["candidates"], 1):
        print(f"  {i}. {c['product']}  score {c['score']:.3f}  value {c['currency']} {c['value']}"
              + (f"  ({c['size_note']})" if c["size_note"] else ""))
        for ch in c["chain"]:
            print(f"       {ch['signal']} ({ch['date']}) → {ch['pain']} — {ch['evidence'][:50]} [{ch['source']}]")
    if not r["candidates"]:
        print(f"  No fit now: {r['reason']}")
    for e in r["excluded"]:
        print(f"  skipped {e['product']}: {e['reason']}")
    for h in r["hooks"]:
        print(f"  hook: {h['signal']} ({h['date']}) — {h['evidence'][:50]}")
    for s in r["skipped_signals"]:
        print(f"  ignored signal: {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
