"""Fetch one signal source from knowledge/sources.yaml (Phase 2, mama-scan).

Deterministic fetching for `access: dataset | rss | page | internal`; `search`
sources are the scout's job (web search). Writes only NEW files under
raw/signals/<date>/<source>/ and never edits or deletes anything in raw/.

- dataset (adapter: datagov): data.gov.sg `datastore_search`. A `collection`
  expands to its child datasets. Rows inside the lookback window are kept
  (newest first by `sort`, or a full scan when `full_scan: true`), filtered by
  `filters` / `exclude` and, with `ssic_from_icp`, by the market's ICP SSIC
  prefixes. One snapshot per item: headline, URL, date, an own-words summary
  (<= 60 words) and the company name + registry ID. No addresses, no officers.
- rss: title, link and date of items inside the lookback window (no text).
- page: robots.txt is honoured; saves `_page-<slug>.json` with short candidate
  strings (link / list / heading text) for the scout to read. No page text.
- internal (contract ends): the latest raw/crm/ export mapped with
  crm_mapping.yaml; contracts ending within `window_days`. The snapshot is the
  export itself (already a raw/ file).

A source without `tos_checked` is refused (rule 9). Items are capped at
`max_items_per_run` (a `capped: true` flag says so).

    python3 scripts/fetch_dataset.py sg-acra-new-cos --run 2026-11-01-0200
    python3 scripts/fetch_dataset.py sg-gebiz-awards --lookback 30 --json
    python3 scripts/fetch_dataset.py sg-acra-new-cos --from-file fixture.json   # offline (selftest)
    python3 scripts/fetch_dataset.py --list

Prints a JSON object {source, items, capped, errors, snapshots} with --json,
otherwise a short summary. Exit 0 on success, 1 when refused or failed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402

UA = "SalesMama/1.0 (B2B signal scan; respects robots.txt)"
DATAGOV = "https://data.gov.sg/api/action/datastore_search"
DATAGOV_META = "https://api-production.data.gov.sg/v2/public/api"
PAGE_SIZE = 1000
MAX_SUMMARY_WORDS = 60
# Never stored, whatever a source maps (rule 8: no addresses, no individuals).
BANNED_FIELDS = re.compile(r"address|block|street|postal|unit_no|level_no|building|officer|owner_name|"
                           r"person|director|nric|phone|email", re.I)


# ----------------------------------------------------------------------------
# Sources
# ----------------------------------------------------------------------------
def load_sources(root: Path) -> tuple[dict, list[dict]]:
    data = mc.load_yaml(root / "knowledge" / "sources.yaml", {}) or {}
    defaults = data.get("defaults") or {}
    return defaults, [s for s in (data.get("sources") or []) if isinstance(s, dict)]


def get_source(root: Path, sid: str) -> dict | None:
    defaults, sources = load_sources(root)
    for s in sources:
        if mc.norm(s.get("id")) == sid:
            return {**defaults, **s}
    return None


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------
def http_get(url: str, tries: int = 4, timeout: int = 40) -> bytes:
    delay = 2.0
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except urllib.error.URLError:
            if attempt < tries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError(f"giving up on {url}")


def get_json(url: str) -> dict:
    return json.loads(http_get(url).decode("utf-8"))


def robots_ok(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.parse(http_get(f"{parts.scheme}://{parts.netloc}/robots.txt", tries=2, timeout=20)
                 .decode("utf-8", "ignore").splitlines())
    except Exception:  # noqa: BLE001 - no robots.txt means no restriction
        return True
    return rp.can_fetch(UA, url)


# ----------------------------------------------------------------------------
# Snapshots
# ----------------------------------------------------------------------------
def clip_words(text: str, n: int = MAX_SUMMARY_WORDS) -> str:
    words = mc.norm(text).split()
    return " ".join(words[:n]) + ("…" if len(words) > n else "")


def snapshot_md(item: dict, source: dict) -> str:
    comp = item["company_text"] + (f" (registry ID {item['reg_id']})" if item.get("reg_id") else "")
    lines = [f"# {item['headline']}", "",
             f"- url: {item['url']}",
             f"- date: {item['date']}",
             f"- source: {source['id']} — {mc.norm(source.get('terms'))}",
             f"- companies: {comp}",
             f"- signal: {item['signal']}", "",
             "## Summary",
             clip_words(item["summary"]), ""]
    return "\n".join(lines)


def write_snapshot(root: Path, folder: Path, item: dict, source: dict, taken: set[str]) -> str:
    """Write one new snapshot; never overwrite an existing raw/ file."""
    base = mc.slugify(item["company_text"])[:60] or "item"
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    taken.add(slug)
    path = folder / f"{slug}.md"
    rel = mc.rel_posix(path, root)
    if path.exists():  # same slug from an earlier run today: keep it, cite it
        return rel
    mc.write_text(path, snapshot_md(item, source))
    return rel


# ----------------------------------------------------------------------------
# Adapters
# ----------------------------------------------------------------------------
def ssic_industry(ssic: str, prefixes: dict) -> str:
    for industry, pre in (prefixes or {}).items():
        if any(ssic.startswith(str(p)) for p in mc.as_list(pre)):
            return str(industry)
    return ""


def datagov_datasets(source: dict) -> list[str]:
    if source.get("datasets"):
        return [str(d) for d in mc.as_list(source["datasets"])]
    meta = get_json(f"{DATAGOV_META}/collections/{source['collection']}/metadata")
    return list(meta["data"]["collectionMetadata"]["childDatasets"])


def datagov_rows(source: dict, since: dt.date, until: dt.date) -> tuple[list[dict], list[str]]:
    """Rows dated within [since, until], from every dataset of the source."""
    fields = source.get("fields") or {}
    want = sorted({str(v) for v in fields.values()} | set((source.get("exclude") or {}).keys()))
    date_field, fmt = source["date_field"], source.get("date_format", "%Y-%m-%d")
    rows, errors = [], []
    for ds in datagov_datasets(source):
        q = {"resource_id": ds, "limit": PAGE_SIZE, "fields": ",".join(want)}
        if source.get("filters"):
            q["filters"] = json.dumps(source["filters"])
        if source.get("sort") and not source.get("full_scan"):
            q["sort"] = source["sort"]
        offset = 0
        while True:
            q["offset"] = offset
            try:
                res = get_json(f"{DATAGOV}?{urllib.parse.urlencode(q)}")["result"]
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{ds}: {exc}".splitlines()[0])
                break
            recs = res.get("records") or []
            older = False
            for r in recs:
                try:
                    d = dt.datetime.strptime(mc.norm(r.get(date_field)), fmt).date()
                except ValueError:
                    continue
                if d < since:
                    older = True
                    continue
                if d <= until:
                    rows.append({**r, "_dataset": ds, "_date": d})
            offset += len(recs)
            # Sorted newest first: stop at the first page that reaches older rows.
            if not recs or offset >= int(res.get("total") or 0) or (older and not source.get("full_scan")):
                break
            time.sleep(0.3)
        time.sleep(0.3)
    return rows, errors


def datagov_items(root: Path, source: dict, rows: list[dict]) -> list[dict]:
    fields = source.get("fields") or {}
    exclude = {k: {mc.norm(v).lower() for v in mc.as_list(vals)}
               for k, vals in (source.get("exclude") or {}).items()}
    prefixes = (mc.load_icp(root)["fit"].get(source["market"]) or {}).get("ssic_prefixes") or {}
    items = []
    for r in sorted(rows, key=lambda x: x["_date"], reverse=True):
        if any(mc.norm(r.get(k)).lower() in vals for k, vals in exclude.items()):
            continue
        rec = {k: mc.norm(r.get(col)) for k, col in fields.items() if not BANNED_FIELDS.search(str(col))}
        if not rec.get("company_text") or rec["company_text"].lower() in ("na", "n/a"):
            continue
        industry = ssic_industry(rec.get("ssic", ""), prefixes) if rec.get("ssic") else ""
        if source.get("ssic_from_icp") and not industry:
            continue
        date = r["_date"].isoformat()
        name = rec["company_text"]
        signal = mc.norm(source.get("signal")) or "unmapped"
        if signal == "new_company":
            headline = f"New company registered: {name}"
            summary = (f"{name} was registered with ACRA on {date} as a "
                       f"{(rec.get('entity_type') or 'company').lower()}. Its primary activity code "
                       f"is {rec.get('ssic') or 'not stated'}, which falls under {industry or 'an unmapped'} "
                       f"in our ICP.")
        elif signal == "contract_win":
            amount = rec.get("amount")
            amt = f" worth about S${float(amount):,.0f}" if amount and re.match(r"^\d+(\.\d+)?$", amount) else ""
            headline = f"Government contract awarded to {name}"
            summary = (f"{name} was awarded a contract by {rec.get('agency') or 'a government agency'} "
                       f"on {date}{amt}. Scope in brief: {clip_words(rec.get('tender', '').lower(), 20)}")
        else:
            headline, summary = f"{name}: {signal}", f"{name} appears in {source['id']} on {date}."
        item = {"market": source["market"], "source": source["id"], "source_type": source.get("type", ""),
                "company_text": name, "signal": signal, "date": date,
                "url": f"https://data.gov.sg/datasets/{r['_dataset']}/view",
                "headline": headline, "summary": summary}
        if rec.get("reg_id"):
            item["reg_id"] = rec["reg_id"].upper()
        if industry:
            item["industry"] = industry
        if rec.get("ssic"):
            item["ssic"] = rec["ssic"]
        if rec.get("entity_type"):
            item["entity_type"] = rec["entity_type"]
        items.append(item)
    return items


def rss_items(source: dict, since: dt.date) -> list[dict]:
    import email.utils
    import xml.etree.ElementTree as ET
    root = ET.fromstring(http_get(source["url"]))
    items = []
    for node in root.iter():
        if node.tag.split("}")[-1] not in ("item", "entry"):
            continue
        get = {c.tag.split("}")[-1]: c for c in node}
        title = mc.norm(get["title"].text) if "title" in get else ""
        link = get.get("link")
        url = mc.norm((link.get("href") if link is not None and link.get("href") else
                       (link.text if link is not None else "")))
        raw_date = mc.norm((get.get("pubDate") or get.get("published") or get.get("updated")).text
                           if (get.get("pubDate") or get.get("published") or get.get("updated")) is not None
                           else "")
        try:
            d = email.utils.parsedate_to_datetime(raw_date).date()
        except (TypeError, ValueError):
            d = mc.to_date(raw_date)
        if not d or d < since:
            continue
        items.append({"market": source["market"], "source": source["id"],
                      "source_type": source.get("type", ""), "headline": title[:200], "url": url,
                      "date": d.isoformat()})
    return items


_TAG_TEXT = re.compile(r"<(a|li|h[1-4]|td|strong|b|span|p)\b[^>]*>(.*?)</\1>", re.S | re.I)


def page_candidates(url: str) -> list[str]:
    raw = http_get(url).decode("utf-8", "ignore")
    raw = re.sub(r"<(script|style|nav|footer|header)\b.*?</\1>", " ", raw, flags=re.S | re.I)
    seen, out = set(), []
    for _, inner in _TAG_TEXT.findall(raw):
        text = html.unescape(re.sub(r"<[^>]+>", " ", inner))
        text = re.sub(r"\s+", " ", text).strip()
        if 3 <= len(text) <= 90 and text.lower() not in seen and not text.lower().startswith(("http", "©")):
            seen.add(text.lower())
            out.append(text)
    return out[:400]


def page_extract(root: Path, source: dict, folder: Path) -> tuple[list[dict], list[str]]:
    targets = [{"url": u} for u in mc.as_list(source.get("urls"))]
    for ev in mc.as_list(source.get("events")):
        if isinstance(ev, dict) and ev.get("exhibitors_url"):
            targets.append({"url": ev["exhibitors_url"], "event": {k: v for k, v in ev.items()
                                                                   if k != "exhibitors_url"}})
    extracts, errors = [], []
    for t in targets:
        url = t["url"]
        if url.lower().endswith(".pdf"):
            errors.append(f"{url}: PDF — read it with the scout's web fetch")
            continue
        if not robots_ok(url):
            errors.append(f"{url}: disallowed by robots.txt — skipped")
            continue
        try:
            cands = page_candidates(url)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {exc}".splitlines()[0])
            continue
        path = folder / f"_page-{mc.slugify(urllib.parse.urlsplit(url).netloc + urllib.parse.urlsplit(url).path)[:80]}.json"
        if not path.exists():
            mc.write_text(path, json.dumps({"url": url, "fetched": mc.now_stamp(), "event": t.get("event"),
                                            "candidates": cands}, indent=1, ensure_ascii=False) + "\n")
        extracts.append({"url": url, "extract": mc.rel_posix(path, root), "candidates": len(cands),
                         **({"event": t["event"]} if t.get("event") else {})})
    return extracts, errors


def internal_items(root: Path, source: dict) -> tuple[list[dict], list[str]]:
    import ingest  # same folder; reuses the CRM mapping rules
    files = sorted((root / "raw" / "crm").glob("*.csv"))
    if not files:
        return [], ["no CRM export in raw/crm/"]
    latest = files[-1]
    rel = mc.rel_posix(latest, root)
    mapping = mc.load_yaml(root / "knowledge" / "crm_mapping.yaml", {}) or {}
    ctx = {"id_types": ingest.market_id_types(root), "industries": ingest.ontology_industries(root),
           "products": ingest.product_ids(root),
           "date_formats": mapping.get("date_formats") or list(ingest.DEFAULT_DATE_FORMATS)}
    res = ingest.Result(rel)
    on = mc.today()
    window = int(source.get("window_days") or ingest.CONTRACT_WINDOW_DAYS)
    items = []
    for i, row in enumerate(mc.read_csv(latest), start=2):
        rec = ingest.map_row(row, mapping, ctx, res, i)
        if not rec or rec.get("market") != source["market"]:
            continue
        ce = mc.to_date(rec.get("contract_end"))
        if not ce or not 0 <= (ce - on).days <= window:
            continue
        item = {"market": rec["market"], "source": source["id"], "source_type": "internal",
                "company_text": rec["name"], "signal": mc.norm(source.get("signal")) or "contract_ending",
                "date": on.isoformat(), "url": "", "snapshot": rel,
                "evidence": f"contract ends {ce.isoformat()} (CRM export)"}
        for k in ("reg_id", "domain", "city", "industry", "employees"):
            if rec.get(k):
                item[k] = rec[k]
        items.append(item)
    return items, []


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def fetch(root: Path, source: dict, on: dt.date, lookback: int | None, cap: int | None,
          from_file: Path | None = None) -> dict:
    sid = source["id"]
    access = mc.norm(source.get("access"))
    lookback = int(lookback if lookback is not None else source.get("lookback_days") or 2)
    cap = int(cap if cap is not None else source.get("max_items_per_run") or 30)
    since = on - dt.timedelta(days=lookback)
    folder = root / "raw" / "signals" / on.isoformat() / sid
    out = {"source": sid, "access": access, "since": since.isoformat(), "items": [], "capped": False,
           "errors": [], "snapshots": 0, "extracts": []}
    if access == "dataset":
        if from_file:
            rows = []
            fmt = source.get("date_format", "%Y-%m-%d")
            for r in json.loads(mc.read_text(from_file)):
                d = dt.datetime.strptime(mc.norm(r.get(source["date_field"])), fmt).date()
                if since <= d <= on:
                    rows.append({**r, "_dataset": r.get("_dataset", "fixture"), "_date": d})
            errors = []
        else:
            rows, errors = datagov_rows(source, since, on)
        items = datagov_items(root, source, rows)
        out["errors"] += errors
    elif access == "rss":
        items = rss_items(source, since)
    elif access == "internal":
        items, errors = internal_items(root, source)
        out["errors"] += errors
    elif access == "page":
        out["extracts"], out["errors"] = page_extract(root, source, folder)
        return out
    else:
        out["errors"].append(f"access `{access}` is not fetched here (search sources are scanned by the scout)")
        return out
    if len(items) > cap:
        items, out["capped"] = items[:cap], True
    taken: set[str] = set()
    for item in items:
        if item.get("snapshot"):
            continue
        if "summary" in item:  # dataset items: deterministic own-words snapshot
            item["snapshot"] = write_snapshot(root, folder, item, source, taken)
            out["snapshots"] += 1
    for item in items:  # keep the hand-off small: summaries live in the snapshot
        item.pop("summary", None)
    out["items"] = items
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch one dataset / rss / page / internal source from "
                                             "knowledge/sources.yaml into raw/signals/.")
    ap.add_argument("source", nargs="?", help="source id from knowledge/sources.yaml")
    ap.add_argument("--date", help="snapshot folder date (default today)")
    ap.add_argument("--lookback", type=int, help="override lookback_days")
    ap.add_argument("--max", type=int, help="override max_items_per_run")
    ap.add_argument("--from-file", help="offline: read dataset rows from this JSON list (tests)")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    ap.add_argument("--list", action="store_true", help="list sources and their access type")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    if args.list:
        defaults, sources = load_sources(root)
        for s in sources:
            print(f"{s.get('id'):24} {s.get('market')!s:4} {s.get('access')!s:9} "
                  f"tos_checked={s.get('tos_checked') or 'MISSING'}")
        return 0
    if not args.source:
        ap.error("source id required (or --list)")
    source = get_source(root, args.source)
    if source is None:
        print(f"Unknown source `{args.source}` (see knowledge/sources.yaml)")
        return 1
    if not source.get("tos_checked"):
        print(f"Refused: `{args.source}` has no tos_checked date in sources.yaml (AGENTS.md rule 9).")
        return 1
    on = mc.to_date(args.date) if args.date else mc.today()
    try:
        res = fetch(root, source, on, args.lookback, args.max,
                    Path(args.from_file) if args.from_file else None)
    except Exception as exc:  # noqa: BLE001
        msg = f"{args.source}: {exc}".splitlines()[0]
        print(json.dumps({"source": args.source, "items": [], "errors": [msg]}) if args.json else f"Failed: {msg}")
        return 1
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(f"{res['source']}: {len(res['items'])} item(s) since {res['since']}"
              f"{' (capped)' if res['capped'] else ''}, {res['snapshots']} snapshot(s), "
              f"{len(res['extracts'])} page extract(s).")
        for e in res["errors"]:
            print(f"  error: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
