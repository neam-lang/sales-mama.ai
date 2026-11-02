"""Claim, assign, release and reassign accounts (AGENTS.md rule 6, PLAN.md §10).

claim.py is the only writer of `owner`, `allocated_on`, `allocated_by` and
`claimed_on`. Every change re-reads the account page, re-checks the hard
constraints and is committed and pushed as one small commit.

    python3 scripts/claim.py <id> [<id>...]                # self-claim (tier C only)
    python3 scripts/claim.py --suggest [N]                 # my eligible tier C pool
    python3 scripts/claim.py --assign <rep> <id> [<id>...] # manager: allocate
    python3 scripts/claim.py --release <id> [<id>...]      # manager, or the owner
    python3 scripts/claim.py --reassign <from> <to> [<id>...]   # manager
    add --dry-run (check only), --no-push (commit locally), --json

Hard constraints (shared with allocate.py through `fits_rep`): the account's
market is live and one of the rep's markets; it fits the rep's territory
(industries, regions, employee band; an empty list means any, an unknown
account value passes with a note); stage is not do_not_contact; its domain
is not in wiki/suppression.csv; the rep is under `max_active`.

No double claims: with a git remote, each attempt pulls, re-reads the pages,
checks they are still free, commits and pushes. A rejected push means
someone else pushed first: the local commit is undone, the pull brings their
change in, and the check runs again on the fresh pages, so an account that
was claimed meanwhile is reported ("already owned by arun") and never
overwritten. The remote's atomic branch update is the lock. Never force-pushes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402

OWNER_FIELDS = ("owner", "allocated_on", "allocated_by", "claimed_on")
MAX_ATTEMPTS = 6


# ----------------------------------------------------------------------------
# Context: knowledge and team, loaded once per run
# ----------------------------------------------------------------------------
class Ctx:
    def __init__(self, root: Path):
        self.root = root
        self.alloc = mc.load_yaml(root / "knowledge" / "allocation.yaml", {}) or {}
        self.markets = mc.load_yaml(root / "knowledge" / "markets.yaml", {}) or {}
        self.live = {str(m).upper() for m in mc.as_list(self.markets.get("live"))} or set(mc.MARKETS)
        self.reload()

    def reload(self) -> None:
        self.reps = {r["id"]: r for r in mc.load_reps(self.root)}
        self.suppressed = {mc.norm(r.get("value")).lower(): mc.norm(r.get("type")).lower()
                           for r in mc.read_csv(self.root / "wiki" / "suppression.csv")}
        self.accounts = {p.id: p for p in mc.iter_pages("account", self.root)}

    def active_count(self, rep_id: str) -> int:
        return sum(1 for p in self.accounts.values()
                   if mc.norm(p.meta.get("owner")) == rep_id and mc.is_active(p.meta))


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def territory_fit(meta: dict, rep: dict) -> tuple[bool, str, list[str]]:
    """(fits, why-not, notes). Empty territory list = any; unknown value passes with a note."""
    terr = rep.get("territory") or {}
    notes: list[str] = []
    inds = [str(x).lower() for x in mc.as_list(terr.get("industries"))]
    ind = mc.norm(meta.get("industry")).lower()
    if inds:
        if not ind:
            notes.append("industry unknown")
        elif ind not in inds:
            return False, f"industry {ind} outside {rep['id']}'s territory", notes
    regions = [str(x).lower() for x in mc.as_list(terr.get("regions"))]
    region = mc.norm(meta.get("region")).lower()
    if regions:
        if not region:
            notes.append("region unknown")
        elif region not in regions:
            return False, f"region {region} outside {rep['id']}'s territory", notes
    band = mc.as_list(terr.get("employees"))
    emp = _num(meta.get("employees"))
    if len(band) == 2:
        if emp is None:
            notes.append("employees unknown")
        elif not float(band[0]) <= emp <= float(band[1]):
            return False, f"{int(emp)} staff outside {band[0]}–{band[1]}", notes
    return True, "", notes


def blocked(meta: dict, ctx: Ctx) -> str:
    """Why nobody may own this lead now ('' if fine): DNC, suppressed domain, closed."""
    if mc.norm(meta.get("stage")) == "do_not_contact":
        return "stage do_not_contact"
    dom = mc.norm(meta.get("domain")).lower().removeprefix("www.")
    if dom and ctx.suppressed.get(dom) == "domain":
        return f"domain {dom} is suppressed"
    if not mc.is_active(meta):
        return f"stage {mc.norm(meta.get('stage'))}"
    return ""


def fits_rep(meta: dict, rep: dict, ctx: Ctx, extra_load: int = 0) -> tuple[bool, str, list[str]]:
    """Hard constraints for giving this account to this rep (claim.py and allocate.py)."""
    if mc.norm(rep.get("role")) == "inactive":
        return False, f"{rep['id']} is inactive", []
    why = blocked(meta, ctx)
    if why:
        return False, why, []
    market = mc.norm(meta.get("market")).upper()
    if market not in mc.MARKETS:
        return False, "account has no market", []
    if market not in ctx.live:
        return False, f"market {market} is not live", []
    if market not in [str(m).upper() for m in mc.as_list(rep.get("markets"))]:
        return False, f"{rep['id']} does not cover {market}", []
    ok, why, notes = territory_fit(meta, rep)
    if not ok:
        return False, why, notes
    cap = int(_num(rep.get("max_active")) or 0)
    if ctx.active_count(rep["id"]) + extra_load >= cap:
        return False, f"{rep['id']} is at capacity ({cap})", notes
    return True, "", notes


# ----------------------------------------------------------------------------
# Operations
# ----------------------------------------------------------------------------
def check_op(op: dict, user: dict, ctx: Ctx, pending: dict[str, int]) -> str:
    """'' if the op may be applied to the current pages, else the reason."""
    kind, acc = op["op"], op["account"]
    page = ctx.accounts.get(acc)
    if page is None:
        return "no account page"
    meta = page.meta
    owner = mc.norm(meta.get("owner"))
    is_mgr = mc.norm(user.get("role")) == "manager"
    if kind == "release":
        if not owner:
            return "not owned"
        if not is_mgr and owner != user["id"]:
            return f"owned by {owner}; only the owner or the manager can release it"
        return ""
    rep = ctx.reps.get(op["rep"])
    if rep is None:
        return f"unknown rep {op['rep']}"
    if kind == "claim":
        if mc.norm(ctx.alloc.get("self_claim")) != "tier_c_only":
            return "self-claim is off in allocation.yaml"
        if owner:
            return "already yours" if owner == user["id"] else f"already owned by {owner}"
        tier = mc.norm(meta.get("tier")).upper()
        if tier != "C":
            return f"tier {tier or '?'}: A/B leads go through the manager's allocation"
    elif kind == "assign":
        if not is_mgr:
            return "only the manager can assign"
        if owner:
            return f"already {'owned by ' + owner}" if owner != rep["id"] else "already assigned to them"
    elif kind == "reassign":
        if not is_mgr:
            return "only the manager can reassign"
        if owner != op.get("from"):
            return f"owned by {owner or 'nobody'}, not {op.get('from')}"
    ok, why, _ = fits_rep(meta, rep, ctx, pending.get(rep["id"], 0))
    return "" if ok else why


def changes_for(op: dict, user: dict, on: str) -> dict:
    if op["op"] == "release":
        return {k: None for k in OWNER_FIELDS}
    if op["op"] == "claim":
        return {"owner": op["rep"], "claimed_on": on}
    return {"owner": op["rep"], "allocated_on": on, "allocated_by": user["id"], "claimed_on": None}


def _log_line(op: dict, user: dict) -> tuple[str, str, str]:
    acc = f"accounts/{op['account']}"
    if op["op"] == "claim":
        return "claim", acc, "self-claimed tier C"
    if op["op"] == "assign":
        return "assign", acc, f"assigned to {op['rep']}" + (f" ({op['note']})" if op.get("note") else "")
    if op["op"] == "reassign":
        return "assign", acc, f"reassigned {op['from']} -> {op['rep']}"
    return "release", acc, f"released to the pool (was {op.get('was') or '?'})"


def write_ops(ops: list[dict], user: dict, ctx: Ctx) -> list[str]:
    """Apply already-checked ops to the files; return the touched repo paths."""
    on = mc.today().isoformat()
    touched = []
    for op in ops:
        page = ctx.accounts[op["account"]]
        op["was"] = mc.norm(page.meta.get("owner"))
        ch = changes_for(op, user, on)
        ch["updated"] = on
        mc.update_frontmatter(page.path, ch)
        touched.append(page.rel)
        o, target, summary = _log_line(op, user)
        mc.append_log(o, user["id"], target, summary, ctx.root)
    touched.append("wiki/log.md")
    return touched


def cl_pause() -> float:
    """Seconds to wait between commit and push (env MAMA_CLAIM_TEST_PAUSE, selftest only)."""
    try:
        return max(0.0, float(os.environ.get("MAMA_CLAIM_TEST_PAUSE", "0")))
    except ValueError:
        return 0.0


def _git_ok(root: Path, args: list[str], timeout: int = 120) -> tuple[bool, str]:
    code, out, err = mc.run_git(args, cwd=root, timeout=timeout)
    return code == 0, (err or out).strip()


def _commit_pending(root: Path, uid: str) -> None:
    """Commit anything already pending in wiki/ so a rejected attempt can be undone
    without losing it (the same paths sync.py commits)."""
    code, out, _ = mc.run_git(["status", "--porcelain", "--", "wiki", "log", "raw", "reps"], cwd=root)
    if code != 0 or not out.strip():
        return
    mc.run_git(["add", "-A", "--", "wiki", "log", "raw", "reps",
                ":(exclude)wiki/index.md", ":(exclude)wiki/books"], cwd=root)
    mc.run_git(["commit", "-q", "-m", f"mama({uid}): save work before claim",
                "--", "wiki", "log", "raw", "reps"], cwd=root)


def apply(root: Path, ops: list[dict], user: dict, dry_run: bool = False, push: bool = True,
          ctx: Ctx | None = None) -> dict:
    """Apply claim/assign/release/reassign ops with compare-and-swap via git push.

    op = {"op": "claim"|"assign"|"release"|"reassign", "account": id, "rep": id,
          "from": id (reassign), "note": str (optional)}
    Returns {"applied": [...], "rejected": [{account, reason}], "pushed": bool,
             "attempts": n, "message": str}.
    """
    ctx = ctx or Ctx(root)
    has_git = mc.run_git(["rev-parse", "--is-inside-work-tree"], cwd=root)[0] == 0
    remote = has_git and push and bool(mc.git_remotes(root)) and bool(mc.git_upstream(root))
    result = {"applied": [], "rejected": [], "pushed": False, "attempts": 0, "message": ""}
    if has_git and not dry_run:
        _commit_pending(root, user["id"])
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result["attempts"] = attempt
        if remote:
            ok, msg = _git_ok(root, ["pull", "-q", "--rebase", "--autostash"])
            if not ok:
                if mc.rebase_in_progress(root):
                    mc.run_git(["rebase", "--abort"], cwd=root)
                result["message"] = f"git pull failed ({msg.splitlines()[-1] if msg else '?'}); nothing claimed"
                result["rejected"] = [{"account": o["account"], "reason": "offline"} for o in ops]
                return result
        ctx.reload()
        good, bad, pending = [], [], {}
        for op in ops:
            why = check_op(op, user, ctx, pending)
            if why:
                bad.append({"account": op["account"], "reason": why})
            else:
                good.append(op)
                if op["op"] != "release":
                    pending[op["rep"]] = pending.get(op["rep"], 0) + 1
        result["applied"], result["rejected"] = good, bad
        if dry_run or not good:
            result["message"] = "dry run" if dry_run else "nothing to change"
            return result
        touched = write_ops(good, user, ctx)
        if not has_git:
            result["message"] = "written (not a git repo)"
            return result
        kinds = sorted({o["op"] for o in good})
        msg = f"mama({user['id']}): {'/'.join(kinds)} " + ", ".join(o["account"] for o in good[:6])
        if len(good) > 6:
            msg += f", +{len(good) - 6} more"
        ok, err = _git_ok(root, ["commit", "-q", "-m", msg, "--", *touched])
        if not ok:
            mc.run_git(["checkout", "--", *touched], cwd=root)
            result["message"] = f"commit failed: {err.splitlines()[-1] if err else '?'}"
            result["applied"] = []
            return result
        if not remote:
            result["message"] = "committed locally (no git remote: nothing pushed)"
            return result
        pause = cl_pause()
        if pause and attempt == 1:  # selftest only: widen the race window
            time.sleep(pause)
        ok, err = _git_ok(root, ["push", "-q"])
        if ok:
            result["pushed"] = True
            result["message"] = "pushed"
            return result
        # Someone pushed first: drop our commit and try again on fresh pages.
        mc.run_git(["reset", "-q", "HEAD~1"], cwd=root)
        mc.run_git(["checkout", "--", *touched], cwd=root)
    result["message"] = f"push kept being rejected after {MAX_ATTEMPTS} attempts; nothing claimed"
    result["rejected"] += [{"account": o["account"], "reason": "busy, try again"} for o in result["applied"]]
    result["applied"] = []
    return result


# ----------------------------------------------------------------------------
# Suggestions for self-claim
# ----------------------------------------------------------------------------
def suggest(user: dict, ctx: Ctx, n: int = 5) -> list[dict]:
    rep = ctx.reps.get(user["id"]) or user
    out = []
    if mc.norm(ctx.alloc.get("self_claim")) != "tier_c_only":
        return out
    for p in ctx.accounts.values():
        m = p.meta
        if mc.norm(m.get("owner")) or mc.norm(m.get("tier")).upper() != "C":
            continue
        ok, _, notes = fits_rep(m, rep, ctx)
        if not ok:
            continue
        why = [f"{mc.norm(m.get('market'))} {mc.norm(m.get('industry')) or 'industry ?'}"]
        if m.get("employees"):
            why.append(f"{m.get('employees')} staff")
        out.append({"account": p.id, "name": mc.norm(m.get("name")), "market": mc.norm(m.get("market")),
                    "score": _num(m.get("score")) or 0.0, "fit": ", ".join(why + notes)})
    out.sort(key=lambda r: (-r["score"], r["account"]))
    return out[:n] if n else out


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def build_ops(args, user: dict) -> list[dict]:
    ids = [mc.link_id(x) for x in args.ids]
    if args.assign:
        rep, *rest = args.assign
        return [{"op": "assign", "account": mc.link_id(a), "rep": rep} for a in rest + ids]
    if args.release:
        return [{"op": "release", "account": mc.link_id(a)} for a in args.release + ids]
    if args.reassign:
        frm, to, *rest = args.reassign
        targets = [mc.link_id(a) for a in rest + ids]
        if not targets:
            targets = [p.id for p in mc.iter_pages("account") if mc.norm(p.meta.get("owner")) == frm
                       and mc.is_active(p.meta)]
        return [{"op": "reassign", "account": a, "rep": to, "from": frm} for a in targets]
    return [{"op": "claim", "account": a, "rep": user["id"]} for a in ids]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Claim (tier C), assign, release or reassign accounts with hard-constraint checks "
                    "and no double claims (pull, check, commit, push; retry on a rejected push).")
    ap.add_argument("ids", nargs="*", help="account ids to self-claim (or extra ids for the mode)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--assign", nargs="+", metavar="REP_THEN_IDS", help="manager: <rep> <id>...")
    g.add_argument("--release", nargs="*", metavar="ID", help="release to the pool (owner or manager)")
    g.add_argument("--reassign", nargs="+", metavar="FROM_TO_IDS",
                   help="manager: <from> <to> [<id>...] (default: all of <from>'s active accounts)")
    g.add_argument("--suggest", nargs="?", const=5, type=int, metavar="N",
                   help="list my top N eligible tier C pool accounts (0 = all)")
    ap.add_argument("--dry-run", action="store_true", help="check only, change nothing")
    ap.add_argument("--no-push", action="store_true", help="commit locally, don't pull/push")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    user = mc.current_user(root)
    if not user:
        print("Unknown user: run mama-setup first (git config user.email must match reps/*.md).")
        return 1
    if args.assign is not None and len(args.assign) < 2 and not args.ids:
        ap.error("--assign needs <rep> <id>...")
    if args.reassign is not None and len(args.reassign) < 2:
        ap.error("--reassign needs <from> <to> [<id>...]")
    ctx = Ctx(root)
    if args.suggest is not None:
        rows = suggest(user, ctx, args.suggest)
        if args.json:
            print(json.dumps(rows, indent=2))
            return 0
        free = int(_num(user.get("max_active")) or 0) - ctx.active_count(user["id"])
        print(f"{user['id']}: {free} free slots; self_claim = {mc.norm(ctx.alloc.get('self_claim')) or 'off'}")
        for i, r in enumerate(rows, 1):
            print(f"  {i}. {r['account']}  score {r['score']:.2f}  — {r['fit']}")
        if not rows:
            print("  No eligible tier C accounts in your markets and territory.")
        return 0
    ops = build_ops(args, user)
    if not ops:
        ap.error("give at least one account id")
    res = apply(root, ops, user, dry_run=args.dry_run, push=not args.no_push, ctx=ctx)
    if args.json:
        print(json.dumps(res, indent=2, default=str))
    else:
        verb = "Would change" if args.dry_run else "Done"
        for o in res["applied"]:
            print(f"{verb}: {o['op']} {o['account']}" + (f" -> {o['rep']}" if o.get("rep") else ""))
        for r in res["rejected"]:
            print(f"Refused: {r['account']} — {r['reason']}")
        print(f"({res['message']}; attempts {res['attempts']})")
    return 0 if res["applied"] or not res["rejected"] else 2


if __name__ == "__main__":
    sys.exit(main())
