"""Build the Singapore geography for 3D Insights (docs/Sales-Mama-3D-Insights-design-spec.md §4).

    python3 scripts/build_geo.py fetch                  # download the open datasets into company-check/data/geo/
    python3 scripts/build_geo.py build                  # write knowledge/geo/sg_planning_areas.geojson + sg_postal_geo.json
    python3 scripts/build_geo.py build --from-dir DIR   # build from GeoJSON files already on disk (tests, offline)
    python3 scripts/build_geo.py check [--json]          # validate, and coverage against the registry

Sources (ids in knowledge/geo/sg_geo.meta.yaml): URA planning-area polygons, plus three point datasets that carry
postal codes (HDB buildings, CHAS clinics, hawker centres). A company is placed in a planning area by:
  1. exact  - its postal code is one of the known points (point-in-polygon), or
  2. prefix - weights of the known points sharing its first 3 digits (>= min_prefix_points), or
  3. sector - weights over its 2-digit sector: knowledge/geo/sg_sectors.yaml when the sector is thinly covered,
              otherwise the known points in the sector.
Methods 2 and 3 are estimates; market_map.py marks them with "≈". Stdlib only; deterministic output.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402

GEO = Path("knowledge/geo")
RAW = Path("company-check/data/geo")
DOWNLOAD_API = "https://api-open.data.gov.sg/v1/public/api/datasets"
UA = "SalesMama/1.0 (open data, 3D insights)"
REGIONS = {"CR": ("central", "Central"), "ER": ("east", "East"), "NR": ("north", "North"),
           "NER": ("north-east", "North-East"), "WR": ("west", "West")}
SMALL = {"of", "and"}


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def meta(root: Path) -> dict:
    return mc.load_yaml(root / GEO / "sg_geo.meta.yaml", {}) or {}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def title(name: str) -> str:
    return " ".join(w if w in SMALL else "-".join(p.capitalize() for p in w.split("-")) for w in name.lower().split())


def polygons(geom: dict) -> list:
    """[[ring, ...], ...] for Polygon and MultiPolygon; coordinates trimmed to lon, lat."""
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return [[[(float(p[0]), float(p[1])) for p in ring] for ring in poly] for poly in polys]


def bbox(polys: list) -> tuple[float, float, float, float]:
    xs = [p[0] for poly in polys for p in poly[0]]
    ys = [p[1] for poly in polys for p in poly[0]]
    return min(xs), min(ys), max(xs), max(ys)


def inside_ring(x: float, y: float, ring: list) -> bool:
    c = False
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def inside(x: float, y: float, polys: list) -> bool:
    for poly in polys:
        if inside_ring(x, y, poly[0]) and not any(inside_ring(x, y, h) for h in poly[1:]):
            return True
    return False


def simplify(ring: list, eps: float) -> list:
    """Douglas-Peucker on a closed ring (eps in degrees); keeps the ring closed and at least 4 points."""
    if len(ring) < 5:
        return ring

    def dp(pts: list) -> list:
        a, b = pts[0], pts[-1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        norm = math.hypot(dx, dy) or 1e-12
        best, idx = 0.0, 0
        for i in range(1, len(pts) - 1):
            d = abs(dy * pts[i][0] - dx * pts[i][1] + b[0] * a[1] - b[1] * a[0]) / norm
            if d > best:
                best, idx = d, i
        if best <= eps:
            return [a, b]
        return dp(pts[: idx + 1])[:-1] + dp(pts[idx:])

    half = len(ring) // 2
    out = dp(ring[: half + 1])[:-1] + dp(ring[half:])
    return out if len(out) >= 4 else ring


def norm_weights(c: dict, digits: int = 3) -> list[list]:
    tot = sum(c.values())
    items = sorted(((k, v / tot) for k, v in c.items() if v > 0), key=lambda kv: (-kv[1], kv[0]))
    out = [[k, round(v, digits)] for k, v in items if round(v, digits) > 0]
    drift = round(1 - sum(w for _, w in out), digits)
    if out and drift:
        out[0][1] = round(out[0][1] + drift, digits)
    return out


# ----------------------------------------------------------------------------
# fetch
# ----------------------------------------------------------------------------
def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fetch(root: Path) -> int:
    out = root / RAW
    out.mkdir(parents=True, exist_ok=True)
    for key, ds in (meta(root).get("datasets") or {}).items():
        url = None
        for _ in range(10):
            try:
                res = _get(f"{DOWNLOAD_API}/{ds['id']}/poll-download")
                url = (res.get("data") or {}).get("url")
                if url:
                    break
                _get(f"{DOWNLOAD_API}/{ds['id']}/initiate-download")
            except Exception as exc:  # noqa: BLE001
                print(f"  {key}: {exc}; retrying")
            time.sleep(6)
        if not url:
            print(f"{key}: download not ready (rate limit?); run fetch again later")
            return 1
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=180) as r:
            (out / f"{key}.geojson").write_bytes(r.read())
        print(f"{key}: {ds['name']} -> {mc.rel_posix(out / (key + '.geojson'), root)}")
        time.sleep(4)
    (out / "fetched.json").write_text(json.dumps({"date": mc.today().isoformat()}) + "\n")
    return 0


# ----------------------------------------------------------------------------
# build
# ----------------------------------------------------------------------------
def load_points(src: Path) -> dict[str, tuple[float, float]]:
    """postal code -> (lon, lat) from the point datasets (first source wins, in this order)."""
    pts: dict[str, tuple[float, float]] = {}
    p = src / "hdb_buildings.geojson"
    if p.is_file():
        for f in json.loads(p.read_text())["features"]:
            code = str(f["properties"].get("POSTAL_COD") or "").strip()
            if re.fullmatch(r"\d{6}", code) and f.get("geometry"):
                ring = polygons(f["geometry"])[0][0]
                pts.setdefault(code, (sum(x for x, _ in ring) / len(ring), sum(y for _, y in ring) / len(ring)))
    p = src / "chas_clinics.geojson"
    if p.is_file():
        for f in json.loads(p.read_text())["features"]:
            m = re.search(r"POSTAL_CD</th>\s*<td>(\d{6})", f["properties"].get("Description") or "")
            if m and f.get("geometry"):
                pts.setdefault(m.group(1), tuple(f["geometry"]["coordinates"][:2]))
    p = src / "hawker_centres.geojson"
    if p.is_file():
        for f in json.loads(p.read_text())["features"]:
            code = str(f["properties"].get("ADDRESSPOSTALCODE") or "").strip()
            if re.fullmatch(r"\d{6}", code) and f.get("geometry"):
                pts.setdefault(code, tuple(f["geometry"]["coordinates"][:2]))
    return pts


def build(root: Path, src: Path) -> int:
    m = meta(root)
    cfg = m.get("build") or {}
    feats = json.loads((src / "planning_areas.geojson").read_text())["features"]
    eps = float(cfg.get("simplify_m", 15)) / 111_320
    areas = []
    for f in sorted(feats, key=lambda f: f["properties"]["PLN_AREA_N"]):
        pr = f["properties"]
        polys = polygons(f["geometry"])
        rid, rname = REGIONS[pr["REGION_C"]]
        areas.append({"id": slug(pr["PLN_AREA_N"]), "name": title(pr["PLN_AREA_N"]), "code": pr["PLN_AREA_C"],
                      "region": rid, "region_name": rname, "area_km2": round(float(pr["SHAPE.AREA"]) / 1e6, 2),
                      "polys": polys, "bbox": bbox(polys)})
    ids = [a["id"] for a in areas]
    if len(set(ids)) != len(ids):
        raise SystemExit("duplicate planning-area ids")

    # 1. exact: known postal points -> area
    pts = load_points(src)
    exact: dict[str, int] = {}
    for code, (x, y) in sorted(pts.items()):
        for i, a in enumerate(areas):
            x1, y1, x2, y2 = a["bbox"]
            if x1 <= x <= x2 and y1 <= y <= y2 and inside(x, y, a["polys"]):
                exact[code] = i
                break
    # 2./3. weights by prefix
    p3: dict[str, Counter] = defaultdict(Counter)
    p2: dict[str, Counter] = defaultdict(Counter)
    for code, i in exact.items():
        p3[code[:3]][ids[i]] += 1
        p2[code[:2]][ids[i]] += 1
    manual = (mc.load_yaml(root / GEO / "sg_sectors.yaml", {}) or {}).get("sectors") or {}
    for sec, w in manual.items():
        bad = [k for k in w if k not in ids]
        if bad:
            raise SystemExit(f"sg_sectors.yaml sector {sec}: unknown area ids {bad}")
        if abs(sum(w.values()) - 1) > 1e-6:
            raise SystemExit(f"sg_sectors.yaml sector {sec}: weights sum to {sum(w.values())}, not 1")
    min_sec, min_pre = int(cfg.get("min_sector_points", 20)), int(cfg.get("min_prefix_points", 10))
    sectors = {}
    for sec in sorted(set(p2) | set(manual)):
        if str(sec) in manual and sum(p2.get(sec, Counter()).values()) < min_sec:
            sectors[str(sec)] = {"method": "manual", "w": norm_weights(manual[str(sec)])}
        elif sum(p2[sec].values()) >= 1:
            sectors[sec] = {"method": "points", "n": sum(p2[sec].values()), "w": norm_weights(p2[sec])}
    prefixes = {k: {"n": sum(c.values()), "w": norm_weights(c)} for k, c in sorted(p3.items())
                if sum(c.values()) >= min_pre and k[:2] not in {s for s, v in sectors.items() if v["method"] == "manual"}}

    # outputs
    out = root / GEO
    fc = {"type": "FeatureCollection", "features": []}
    for a in areas:
        polys = []
        for poly in a["polys"]:
            rings = [[[round(x, 5), round(y, 5)] for x, y in simplify(r, eps)] for r in poly]
            polys.append([r for r in rings if len(r) >= 4])
        geom = {"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1 else \
            {"type": "MultiPolygon", "coordinates": polys}
        fc["features"].append({"type": "Feature", "properties": {k: a[k] for k in
                                                                 ("id", "name", "code", "region", "region_name", "area_km2")},
                               "geometry": geom})
    (out / "sg_planning_areas.geojson").write_text(json.dumps(fc, separators=(",", ":")) + "\n")
    fetched = src / "fetched.json"
    built = json.loads(fetched.read_text())["date"] if fetched.is_file() else mc.today().isoformat()
    geo = {"version": 1, "market": "SG", "data_date": built, "areas": ids,
           "regions": {a["id"]: a["region"] for a in areas},
           "exact": {k: v for k, v in sorted(exact.items())}, "prefixes": prefixes, "sectors": sectors}
    (out / "sg_postal_geo.json").write_text(json.dumps(geo, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(f"areas {len(areas)} · postal points {len(pts):,} · placed exactly {len(exact):,} · "
          f"prefix weights {len(prefixes)} · sectors {len(sectors)} "
          f"({sum(1 for s in sectors.values() if s['method'] == 'manual')} manual)")
    print(f"wrote {GEO}/sg_planning_areas.geojson ({(out / 'sg_planning_areas.geojson').stat().st_size // 1024} KB), "
          f"{GEO}/sg_postal_geo.json ({(out / 'sg_postal_geo.json').stat().st_size // 1024} KB)")
    return 0


# ----------------------------------------------------------------------------
# check
# ----------------------------------------------------------------------------
def check(root: Path, as_json: bool) -> int:
    errs = []
    fc = json.loads((root / GEO / "sg_planning_areas.geojson").read_text())
    geo = json.loads((root / GEO / "sg_postal_geo.json").read_text())
    ids = [f["properties"]["id"] for f in fc["features"]]
    if len(ids) != 55 or len(set(ids)) != 55:
        errs.append(f"expected 55 unique planning areas, got {len(set(ids))}")
    if ids != geo["areas"]:
        errs.append("sg_postal_geo.json areas differ from the GeoJSON")
    for sec, s in geo["sectors"].items():
        if abs(sum(w for _, w in s["w"]) - 1) > 0.002:
            errs.append(f"sector {sec} weights do not sum to 1")
    res = {"areas": len(ids), "regions": dict(Counter(f["properties"]["region"] for f in fc["features"])),
           "exact_codes": len(geo["exact"]), "sectors": len(geo["sectors"]), "errors": errs}
    reg = root / "company-check" / "data" / "registry.sqlite"
    if reg.is_file():
        import sqlite3
        con = sqlite3.connect(reg)
        codes = [str(p).zfill(6) for (p,) in con.execute("SELECT postal FROM live WHERE postal IS NOT NULL AND postal != ''")]
        n = len(codes)
        ex = sum(1 for c in codes if c in geo["exact"])
        pre = sum(1 for c in codes if c not in geo["exact"] and c[:3] in geo["prefixes"])
        sec = sum(1 for c in codes if c not in geo["exact"] and c[:3] not in geo["prefixes"] and c[:2] in geo["sectors"])
        res["registry"] = {"live_with_postal": n, "exact_pct": round(100 * ex / n, 1), "prefix_pct": round(100 * pre / n, 1),
                           "sector_pct": round(100 * sec / n, 1), "unplaced": n - ex - pre - sec}
    print(json.dumps(res, indent=2) if as_json else "\n".join(f"{k}: {v}" for k, v in res.items()))
    return 1 if errs else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the Singapore geography for 3D Insights.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="download the open datasets into company-check/data/geo/")
    b = sub.add_parser("build", help="write knowledge/geo/sg_planning_areas.geojson and sg_postal_geo.json")
    b.add_argument("--from-dir", help="folder with planning_areas.geojson and the point files")
    c = sub.add_parser("check", help="validate the geo files and report coverage against the registry")
    c.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    if args.cmd == "fetch":
        return fetch(root)
    if args.cmd == "build":
        src = Path(args.from_dir) if args.from_dir else root / RAW
        if not (src / "planning_areas.geojson").is_file():
            print(f"no planning_areas.geojson in {src}: run `python3 scripts/build_geo.py fetch` first")
            return 1
        return build(root, src)
    return check(root, args.json)


if __name__ == "__main__":
    sys.exit(main())
