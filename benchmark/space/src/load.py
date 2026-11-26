"""Load submissions (results/*.json) into leaderboard tables."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .scoring import BENCH_VERSION, LIVE, RANKED_PROFILE, TRACKS, ci95, competition_ranks, shs

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
REQUIRED = ("schema", "id", "harness", "model", "benchmark", "tracks")


def validate(sub: dict) -> list[str]:
    errs = [f"missing `{k}`" for k in REQUIRED if k not in sub]
    if errs:
        return errs
    if not str(sub["schema"]).startswith("shl/"):
        errs.append("`schema` must start with `shl/`")
    for k in ("name", "runtime"):
        if not (sub.get("harness") or {}).get(k):
            errs.append(f"`harness.{k}` is required")
    if not (sub.get("model") or {}).get("name"):
        errs.append("`model.name` is required")
    if (sub.get("benchmark") or {}).get("split") not in ("dev", "test"):
        errs.append("`benchmark.split` must be dev or test")
    known = {t.key for t in TRACKS}
    for k, v in (sub.get("tracks") or {}).items():
        if k not in known:
            errs.append(f"unknown track `{k}` (known: {', '.join(sorted(known))})")
            continue
        s = v.get("score") if isinstance(v, dict) else v
        try:
            if not 0 <= float(s) <= 1:
                errs.append(f"tracks.{k}.score must be in [0, 1]")
        except (TypeError, ValueError):
            errs.append(f"tracks.{k}.score is not a number")
    s = sub.get("safety") or {}
    if s and (s.get("runs") is None or s.get("critical_violations") is None):
        errs.append("`safety` needs `runs` and `critical_violations`")
    return errs


def load_submissions(folder: Path = RESULTS_DIR) -> list[dict]:
    subs = []
    for p in sorted(folder.glob("*.json")):
        try:
            sub = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not validate(sub):
            subs.append(sub)
    return subs


LEGACY_VERSION = "SHB-SEA v0.1"


def unranked_reason(sub: dict) -> str:
    """Why a full row is shown but not ranked ('' if rankable): another protocol version, or a dev
    diagnostic run that showed the real task IDs to the harness."""
    b = sub.get("benchmark") or {}
    if b.get("task_ids_exposed"):
        return "task IDs exposed to the harness (diagnostic)"
    if b.get("version") != BENCH_VERSION:
        return f"{b.get('version') or 'unknown version'} (this board ranks {BENCH_VERSION})"
    if b.get("version") == LEGACY_VERSION:  # v0.1 rows predate these fields: missing means v0.1 defaults
        if b.get("prompt_profile") not in (None, RANKED_PROFILE):
            return f"prompt profile {b.get('prompt_profile')} (this board ranks {RANKED_PROFILE})"
        return ""
    if b.get("task_ids_exposed") is not False:
        return "task_ids_exposed not stated"
    if b.get("prompt_profile") != RANKED_PROFILE:
        return f"prompt profile {b.get('prompt_profile') or 'not stated'} (this board ranks {RANKED_PROFILE})"
    return ""


def _pct(x):
    return None if x is None else round(100 * x, 1)


def row(sub: dict) -> dict:
    r = shs(sub)
    h, m, b = sub["harness"], sub["model"], sub["benchmark"]
    eff, safe = sub.get("efficiency") or {}, sub.get("safety") or {}
    status = "verified" if sub.get("verified") else "self-reported"
    if not r["full"]:
        status += " · partial"
    why_unranked = unranked_reason(sub)
    if why_unranked:
        status += f" · not ranked: {why_unranked}"
    out = {
        "Harness": f"[{h['name']}]({h['url']})" if h.get("url") else h["name"],
        "Runtime": h.get("runtime", ""),
        "Model": m["name"],
        # SHS is only defined for full coverage of the live tracks; partial rows show capability only.
        "SHS": round(r["shs"], 1) if (r["shs"] is not None and r["full"]) else None,
        "95% CI": "" if not r["full"] or not (ci := ci95(sub)) else f"{ci[0]:.1f}–{ci[1]:.1f}",
        "Capability": _pct(r["capability"]),
        "Trust": _pct(r["trust"]),
        "Coverage": f"{round(100 * r['coverage'])}%",
        "Split": b.get("split", ""),
        "Status": status,
        "pass^k": _pct(sub.get("reliability", {}).get("pass_hat_k")),
        "k": sub.get("trials"),
        "$/task": eff.get("usd_per_task"),
        "min/task": eff.get("minutes_per_task"),
        "Crit. viol. %": _pct(r["cvr"]),
        "Inj. ASR %": _pct(safe.get("injection_asr")),
        "Open weights": "yes" if m.get("open_weights") else "no",
        "Open harness": "yes" if h.get("open_source") else "no",
        "Date": sub.get("date", ""),
        "Flags": "; ".join(sub.get("flags", [])),
        "_full": r["full"],
        "_rankable": bool(r["full"]) and not why_unranked,
        "_shs": r["shs"] if r["shs"] is not None else -1,
        "_id": sub["id"],
    }
    for t in TRACKS:
        if t.live:
            out[t.name] = _pct(r["scores"].get(t.key))
    out["_sub"] = sub
    return out


def leaderboard_df(subs: list[dict]) -> pd.DataFrame:
    if not subs:
        return pd.DataFrame()
    df = pd.DataFrame([row(s) for s in subs])
    df = df.sort_values(["_rankable", "_full", "_shs"], ascending=[False, False, False]).reset_index(drop=True)
    full = df[df["_rankable"]]
    ranks = competition_ranks(list(full["_sub"])) if len(full) else []
    rank_of = dict(zip(full.index, ranks))
    best = full["_shs"].max() if len(full) else None
    df.insert(0, "#", [str(rank_of[i]) if i in rank_of else "—" for i in df.index])
    df.insert(df.columns.get_loc("SHS") + 1, "vs leader",
              [round(v - best, 1) if (best is not None and f) else None for v, f in zip(df["_shs"], df["_rankable"])])
    return df
