"""Download Singapore registry open data and build the local index for /company-check (ADR-0008).

    python3 scripts/registry_data.py refresh            # download what changed on data.gov.sg, then build
    python3 scripts/registry_data.py refresh --force    # download everything again
    python3 scripts/registry_data.py refresh --from-dir DIR   # build from CSVs already on disk (tests, offline)
    python3 scripts/registry_data.py stats [--json]     # counts, freshness and the cross-check

Datasets (ids in knowledge/company_check.yaml): ACRA Information on Corporate Entities
(collection 2, 27 CSVs, refreshed mid-month), the ACRA UEN register (~2.12M rows), BCA
registered contractors, GeBIZ awards and HDB property information.

Everything goes to company-check/data/ (git-ignored): data/<YYYY-MM>/<kind>/<dataset>.csv,
registry.sqlite and manifest.json. Only the latest month's CSVs are kept. The index is a
rebuildable cache of public data, never the system of record.

Contains information from datasets on data.gov.sg made available under the terms of the
Singapore Open Data Licence version 1.0 (https://data.gov.sg/open-data-licence).
An optional API key raises rate limits: env DATAGOV_API_KEY or ~/.config/sales-mama/datagov.json {"key": "..."}.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402
from fetch_dataset import DATAGOV_META, UA  # noqa: E402
from resolve import norm_name  # noqa: E402

DOWNLOAD_API = "https://api-open.data.gov.sg/v1/public/api/datasets"
KINDS = ("acra", "uen", "bca", "gebiz", "hdb")
LICENCE = ("Contains information from {what} accessed on {date} from data.gov.sg, made available under the "
           "terms of the Singapore Open Data Licence version 1.0 (https://data.gov.sg/open-data-licence).")
BATCH = 20000
csv.field_size_limit(10_000_000)
STREET_ABBR = {"STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "DRIVE": "DR", "CRESCENT": "CRES",
               "CENTRAL": "CTRL", "NORTH": "NTH", "SOUTH": "STH", "CLOSE": "CL", "LORONG": "LOR",
               "UPPER": "UPP", "BUKIT": "BT", "JALAN": "JLN", "TANJONG": "TG", "KAMPONG": "KG",
               "PLACE": "PL", "TERRACE": "TER", "HEIGHTS": "HTS", "GARDENS": "GDNS", "PARK": "PK",
               "COMMONWEALTH": "C'WEALTH", "INDUSTRIAL": "IND", "MARKET": "MKT", "SQUARE": "SQ",
               "BOULEVARD": "BLVD", "EAST": "E", "WEST": "W"}


# ----------------------------------------------------------------------------
# Paths and config
# ----------------------------------------------------------------------------
def data_dir(root: Path) -> Path:
    return root / "company-check" / "data"


def db_path(root: Path) -> Path:
    return data_dir(root) / "registry.sqlite"


def config(root: Path) -> dict:
    data = mc.load_yaml(root / "knowledge" / "company_check.yaml", {}) or {}
    return data if isinstance(data, dict) else {}


def manifest(root: Path) -> dict:
    p = data_dir(root) / "manifest.json"
    try:
        return json.loads(mc.read_text(p)) if p.is_file() else {}
    except ValueError:
        return {}


def save_manifest(root: Path, data: dict) -> None:
    p = data_dir(root) / "manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    mc.write_text(p, json.dumps(data, indent=2) + "\n")


def api_key() -> str:
    key = os.environ.get("DATAGOV_API_KEY", "").strip()
    if key:
        return key
    try:
        import channels
        return str(channels.read_secret("datagov.json").get("key", "")).strip()
    except Exception:  # noqa: BLE001
        return ""


# ----------------------------------------------------------------------------
# Normalisers (shared with company_check.py)
# ----------------------------------------------------------------------------
def na(value) -> str:
    v = mc.norm(value)
    return "" if v.lower() in ("", "na", "n/a", "nil", "-") else v


def norm_street(value: str) -> str:
    words = re.sub(r"[^A-Z0-9' ]+", " ", na(value).upper()).split()
    return " ".join(STREET_ABBR.get(w, w) for w in words)


def norm_block(value: str) -> str:
    return re.sub(r"^(BLK|BLOCK)\s*", "", na(value).upper()).strip()


def address_key(postal: str, level: str, unit: str) -> str:
    return "|".join(na(x).upper().lstrip("0") if i else na(x) for i, x in enumerate((postal, level, unit)))


def iso(value: str) -> str:
    """ISO date from ACRA (YYYY-MM-DD) or GeBIZ (D/M/YYYY); '' if empty."""
    v = na(value)
    if not v:
        return ""
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", v)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    d = mc.to_date(v[:10])
    return d.isoformat() if d else ""


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def read_rows(path: Path):
    with open(path, encoding="utf-8-sig", newline="", errors="replace") as fh:
        reader = csv.DictReader(fh)
        reader.fieldnames = [_key(f) for f in (reader.fieldnames or [])]
        yield from reader


# ----------------------------------------------------------------------------
# Download
# ----------------------------------------------------------------------------
def _get(url: str, tries: int = 5) -> dict:
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if api_key():
        headers["x-api-key"] = api_key()
    delay = 6.0
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt < tries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError(f"giving up on {url}")


def dataset_ids(cfg: dict) -> list[tuple[str, str]]:
    ds = cfg.get("datasets") or {}
    out = []
    meta = _get(f"{DATAGOV_META}/collections/{ds.get('acra_collection', 2)}/metadata")
    out += [("acra", d) for d in meta["data"]["collectionMetadata"]["childDatasets"]]
    for kind, key in (("uen", "uen_register"), ("bca", "bca_contractors"), ("gebiz", "gebiz_awards"),
                      ("hdb", "hdb_blocks")):
        if ds.get(key):
            out.append((kind, str(ds[key])))
    return out


def download(dataset: str, dest: Path, tries: int = 3) -> None:
    for attempt in range(tries):
        try:
            return _download(dataset, dest)
        except (urllib.error.URLError, TimeoutError, ConnectionError, RuntimeError):
            if attempt == tries - 1:
                raise
            time.sleep(15 * (attempt + 1))


def _download(dataset: str, dest: Path) -> None:
    _get(f"{DOWNLOAD_API}/{dataset}/initiate-download")
    url = ""
    for _ in range(60):
        res = _get(f"{DOWNLOAD_API}/{dataset}/poll-download")
        data = res.get("data") or {}
        if data.get("status") == "DOWNLOAD_SUCCESS" and data.get("url"):
            url = data["url"]
            break
        time.sleep(3)
    if not url:
        raise RuntimeError(f"{dataset}: download not ready after 3 minutes")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=600) as resp, \
            open(tmp, "wb") as fh:
        shutil.copyfileobj(resp, fh, length=1 << 20)
    os.replace(tmp, dest)


def refresh(root: Path, cfg: dict, only: list[str], force: bool, log=print) -> dict:
    man = manifest(root)
    month = mc.today().strftime("%Y-%m")
    files = man.get("files") or {}
    changed = 0
    for kind, ds in dataset_ids(cfg):
        if only and kind not in only:
            continue
        meta = _get(f"{DATAGOV_META}/datasets/{ds}/metadata").get("data") or {}
        updated = meta.get("lastUpdatedAt", "")
        prev = files.get(ds) or {}
        old = root / prev["file"] if prev.get("file") else None
        if not force and prev.get("lastUpdatedAt") == updated and old and old.is_file():
            continue
        dest = data_dir(root) / month / kind / f"{ds}.csv"
        if not (dest.is_file() and dest.stat().st_size > 0 and not force and not prev):
            # (a file already fetched this month but not yet in the manifest is reused: resume after a failure)
            log(f"downloading {kind} {ds} (updated {updated or '?'}) …")
            download(ds, dest)
            time.sleep(6)  # 2 downloads per 10 s without a key
        files[ds] = {"kind": kind, "name": meta.get("name", ""), "lastUpdatedAt": updated,
                     "file": mc.rel_posix(dest, root), "downloaded": mc.now_stamp()}
        changed += 1
        man.update(files=files)
        save_manifest(root, man)  # progress survives a failure
    man.update(files=files, refreshed=mc.now_stamp())
    save_manifest(root, man)
    # keep only the files the manifest points at
    keep = {(root / f["file"]).resolve() for f in files.values() if f.get("file")}
    for p in data_dir(root).glob("*/*/*.csv"):
        if p.resolve() not in keep:
            p.unlink()
    for d in sorted(data_dir(root).glob("*/*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    for d in data_dir(root).glob("*"):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    return {"changed": changed}


# ----------------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE live (uen TEXT PRIMARY KEY, name TEXT, name_norm TEXT, entity_type TEXT, company_type TEXT,
  status TEXT, reg_date TEXT, ar_date TEXT, acct_due TEXT, address_type TEXT, block TEXT, street TEXT,
  level TEXT, unit TEXT, building TEXT, postal TEXT, other1 TEXT, other2 TEXT, ssic TEXT, ssic_desc TEXT,
  activity TEXT, officers INTEGER, former_names INTEGER, auditors INTEGER);
CREATE TABLE all_entities (uen TEXT, name TEXT, name_norm TEXT, status TEXT, entity_type TEXT, source TEXT);
CREATE VIRTUAL TABLE names_fts USING fts5(name_norm, uen UNINDEXED);
CREATE TABLE address_counts (key TEXT PRIMARY KEY, n INTEGER);
CREATE TABLE bca (uen TEXT, company_name TEXT, workhead TEXT, grade TEXT, expiry TEXT);
CREATE TABLE gebiz (name_norm TEXT, supplier TEXT, award_date TEXT, agency TEXT, amount REAL, description TEXT);
CREATE TABLE hdb (key TEXT PRIMARY KEY, residential TEXT, commercial TEXT);
"""
INDEXES = """
CREATE INDEX all_uen ON all_entities(uen);
CREATE INDEX all_name ON all_entities(name_norm);
CREATE INDEX live_name ON live(name_norm);
CREATE INDEX bca_uen ON bca(uen);
CREATE INDEX gebiz_name ON gebiz(name_norm);
"""


def _files(base: Path, kind: str) -> list[Path]:
    return sorted((base / kind).glob("*.csv")) if (base / kind).is_dir() else []


def _num(value) -> int:
    try:
        return int(float(na(value) or 0))
    except ValueError:
        return 0


def build(root: Path, cfg: dict, src: Path | None = None, log=print) -> dict:
    """Build registry.sqlite from CSVs in `src` (<kind>/*.csv) or from the manifest's files."""
    live_set = set(mc.as_list(cfg.get("live_statuses")) or ["Live Company", "Live"])
    if src is not None:
        by_kind = {k: _files(src, k) for k in KINDS}
    else:
        files = (manifest(root).get("files") or {}).values()
        by_kind = {k: [root / f["file"] for f in files if f.get("kind") == k and (root / f["file"]).is_file()]
                   for k in KINDS}
    if not by_kind["acra"]:
        raise RuntimeError("no ACRA files: run `python3 scripts/registry_data.py refresh` first")
    out = db_path(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;" + SCHEMA)
    counts = {"acra_rows": 0, "acra_status": {}, "live_by_type": {}, "uen_rows": 0, "uen_status": {}}
    acra_uens: set[str] = set()

    live_rows, all_rows, addr = [], [], {}

    def flush() -> None:
        con.executemany("INSERT OR REPLACE INTO live VALUES (" + ",".join("?" * 24) + ")", live_rows)
        con.executemany("INSERT INTO names_fts VALUES (?,?)", [(r[2], r[0]) for r in live_rows])
        con.executemany("INSERT INTO all_entities VALUES (?,?,?,?,?,?)", all_rows)
        live_rows.clear()
        all_rows.clear()

    for f in by_kind["acra"]:
        log(f"indexing {f.name} …")
        for r in read_rows(f):
            uen = na(r.get("uen")).upper()
            if not uen:
                continue
            status, etype = na(r.get("entity_status_description")), na(r.get("entity_type_description"))
            name = na(r.get("entity_name"))
            counts["acra_rows"] += 1
            counts["acra_status"][status] = counts["acra_status"].get(status, 0) + 1
            acra_uens.add(uen)
            nn = norm_name(name)
            all_rows.append((uen, name, nn, status, etype, "acra"))
            if status in live_set:
                counts["live_by_type"][etype] = counts["live_by_type"].get(etype, 0) + 1
                former = sum(1 for i in range(1, 16) if na(r.get(f"former_entity_name{i}")))
                auditors = sum(1 for i in range(1, 6) if na(r.get(f"uen_of_audit_firm{i}")))
                live_rows.append((uen, name, nn, etype, na(r.get("company_type_description")), status,
                                  iso(r.get("registration_incorporation_date")), iso(r.get("annual_return_date")),
                                  iso(r.get("account_due_date")), na(r.get("address_type")), na(r.get("block")),
                                  na(r.get("street_name")), na(r.get("level_no")), na(r.get("unit_no")),
                                  na(r.get("building_name")), na(r.get("postal_code")),
                                  na(r.get("other_address_line1")), na(r.get("other_address_line2")),
                                  na(r.get("primary_ssic_code")), na(r.get("primary_ssic_description")),
                                  na(r.get("primary_user_described_activity")), _num(r.get("no_of_officers")),
                                  former, auditors))
                k = address_key(r.get("postal_code"), r.get("level_no"), r.get("unit_no"))
                if na(r.get("postal_code")):
                    addr[k] = addr.get(k, 0) + 1
            if len(all_rows) >= BATCH:
                flush()
    flush()
    con.executemany("INSERT INTO address_counts VALUES (?,?)", addr.items())

    for f in by_kind["uen"]:
        log(f"indexing {f.name} (UEN register) …")
        for r in read_rows(f):
            uen = na(r.get("uen")).upper()
            if not uen:
                continue
            status = na(r.get("uen_status_desc") or r.get("uen_status"))
            counts["uen_rows"] += 1
            counts["uen_status"][status] = counts["uen_status"].get(status, 0) + 1
            if uen not in acra_uens:
                name = na(r.get("entity_name"))
                all_rows.append((uen, name, norm_name(name), status, na(r.get("entity_type_desc")), "uen_register"))
            if len(all_rows) >= BATCH:
                flush()
    flush()

    for f in by_kind["bca"]:
        con.executemany("INSERT INTO bca VALUES (?,?,?,?,?)",
                        [(na(r.get("uen_no")).upper(), na(r.get("company_name")), na(r.get("workhead")),
                          na(r.get("grade")), iso(r.get("expiry_date"))) for r in read_rows(f)])
    for f in by_kind["gebiz"]:
        rows = []
        for r in read_rows(f):
            sup = na(r.get("supplier_name"))
            if not sup or "award" not in na(r.get("tender_detail_status")).lower():
                continue
            try:
                amt = float(re.sub(r"[^\d.]", "", na(r.get("awarded_amt"))) or 0)
            except ValueError:
                amt = 0.0
            rows.append((norm_name(sup), sup, iso(r.get("award_date")), na(r.get("agency")), amt,
                         na(r.get("tender_description"))[:200]))
        con.executemany("INSERT INTO gebiz VALUES (?,?,?,?,?,?)", rows)
    for f in by_kind["hdb"]:
        hdb = {}
        for r in read_rows(f):
            key = norm_block(r.get("blk_no")) + "|" + norm_street(r.get("street"))
            hdb[key] = (na(r.get("residential")).upper(), na(r.get("commercial")).upper())
        con.executemany("INSERT OR REPLACE INTO hdb VALUES (?,?,?)", [(k, a, b) for k, (a, b) in hdb.items()])

    con.executescript(INDEXES)
    counts["live"] = sum(counts["live_by_type"].values())
    counts["bca_rows"] = con.execute("SELECT COUNT(*) FROM bca").fetchone()[0]
    counts["gebiz_awards"] = con.execute("SELECT COUNT(*) FROM gebiz").fetchone()[0]
    counts["hdb_blocks"] = con.execute("SELECT COUNT(*) FROM hdb").fetchone()[0]
    counts["shared_addresses"] = con.execute(
        "SELECT COUNT(*) FROM address_counts WHERE n >= ?",
        (int((cfg.get("filters") or {}).get("shared_address_warn", 20)),)).fetchone()[0]
    acra_updated = max([v.get("lastUpdatedAt", "") for v in (manifest(root).get("files") or {}).values()
                        if v.get("kind") == "acra"] or [""])
    meta = {"built": mc.now_stamp(), "acra_updated": acra_updated, "counts": json.dumps(counts),
            "source": "from-dir" if src is not None else "data.gov.sg"}
    con.executemany("INSERT INTO meta VALUES (?,?)", meta.items())
    con.commit()
    con.close()
    os.replace(tmp, out)
    man = manifest(root)
    man.update(built=meta["built"], counts=counts, acra_updated=acra_updated, crosscheck=crosscheck(counts, cfg))
    save_manifest(root, man)
    return counts


def crosscheck(counts: dict, cfg: dict) -> list[dict]:
    cc = cfg.get("crosscheck") or {}
    tol = float(cc.get("tolerance", 0.05))
    out = []
    for key, got in (("uen_register_rows", counts.get("uen_rows", 0)), ("live_entities", counts.get("live", 0))):
        want = cc.get(key)
        if not want:
            continue
        diff = (got - want) / want if want else 0
        out.append({"check": key, "expected": want, "got": got, "diff": round(diff, 4), "ok": abs(diff) <= tol})
    return out


def stats(root: Path) -> dict:
    man = manifest(root)
    db = db_path(root)
    return {"index": mc.rel_posix(db, root) if db.is_file() else None, "built": man.get("built"),
            "acra_updated": man.get("acra_updated"), "refreshed": man.get("refreshed"),
            "counts": man.get("counts") or {}, "crosscheck": man.get("crosscheck") or [],
            "files": len(man.get("files") or {})}


def _print_stats(s: dict) -> None:
    c = s["counts"]
    if not s["index"]:
        print("No registry index yet: run `python3 scripts/registry_data.py refresh`.")
        return
    print(f"Registry index built {s['built']} · ACRA data updated {s['acra_updated'] or '?'}")
    print(f"  UEN register rows: {c.get('uen_rows', 0):,}  ({', '.join(f'{k} {v:,}' for k, v in sorted(c.get('uen_status', {}).items()))})")
    print(f"  ACRA entity rows:  {c.get('acra_rows', 0):,}")
    print(f"  Live entities:     {c.get('live', 0):,}")
    for k, v in sorted(c.get("live_by_type", {}).items(), key=lambda x: -x[1]):
        print(f"    {k or '(blank)'}: {v:,}")
    print(f"  Status breakdown:  " + ", ".join(f"{k or '(blank)'} {v:,}"
                                             for k, v in sorted(c.get("acra_status", {}).items(), key=lambda x: -x[1])))
    print(f"  BCA contractors {c.get('bca_rows', 0):,} · GeBIZ awards {c.get('gebiz_awards', 0):,} · "
          f"HDB blocks {c.get('hdb_blocks', 0):,} · shared addresses {c.get('shared_addresses', 0):,}")
    for x in s["crosscheck"]:
        print(f"  Cross-check {x['check']}: expected ~{x['expected']:,}, got {x['got']:,} "
              f"({x['diff']:+.1%}) {'ok' if x['ok'] else 'CHECK: outside tolerance'}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Download ACRA, BCA, GeBIZ and HDB open data from data.gov.sg and "
                                             "build the local index for /company-check.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rf = sub.add_parser("refresh", help="download what changed, then build the index")
    rf.add_argument("--only", default="", help=f"comma list of {', '.join(KINDS)}")
    rf.add_argument("--force", action="store_true", help="download everything again")
    rf.add_argument("--from-dir", help="build from <dir>/<kind>/*.csv instead of downloading")
    st = sub.add_parser("stats", help="counts, freshness and the cross-check")
    st.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    cfg = config(root)
    if args.cmd == "stats":
        s = stats(root)
        print(json.dumps(s, indent=2)) if args.json else _print_stats(s)
        return 0
    try:
        if args.from_dir:
            build(root, cfg, Path(args.from_dir).expanduser())
        else:
            only = [k.strip() for k in args.only.split(",") if k.strip()]
            res = refresh(root, cfg, only, args.force)
            if res["changed"] or not db_path(root).is_file():
                build(root, cfg)
            else:
                print("Nothing changed on data.gov.sg since the last refresh.")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed: {type(exc).__name__}: {exc}")
        return 1
    _print_stats(stats(root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
