"""Book, move and close appointments (ADR-0010). A tool: JSON in and out, no presentation.

log/appointments.csv is append-only and event-sourced: every change appends a row and the latest
row per id is the appointment's current state, so reschedules and cancellations keep their history.

    python3 scripts/appointments.py add --account harbourlight-foods --start "2026-11-18 14:00" --minutes 45 \\
        --contact rachel-goh-harbourlight-foods --title "Pilot scoping" --status confirmed --json
    python3 scripts/appointments.py confirm|cancel|held|no-show <id> [--json]
    python3 scripts/appointments.py reschedule <id> --start "2026-11-19 15:00" [--minutes 30] [--json]
    python3 scripts/appointments.py list [--rep me|<id>|all] [--from YYYY-MM-DD] [--to YYYY-MM-DD] --json

Times are read in the account's market time zone (knowledge/markets.yaml) and stored as ISO with that
offset. Refused (exit 1): unknown user, someone else's account (rules 6, 16), an inactive account, a
contact not on the account page (rule 5), a suppressed contact or domain (rule 2), an unknown id.
Warned but booked: market holiday, weekend, outside 08:00–19:00 local, overlap with the rep's other
appointments or a Google Calendar busy block (busy_import.py), a date in the past. A confirmed booking appends the `meeting_booked` touch; `held` does
not (crm_update.py writes `meeting_held` in mama-handover). Never changes stage or owner; never
contacts anyone.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402

OPEN_HOURS = (8, 19)          # local business hours used for the after-hours warning
CHANGES = {"confirm": "confirmed", "cancel": "cancelled", "held": "held", "no-show": "no_show"}


class Refused(ValueError):
    pass


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def parse_start(text: str, tz: dt.tzinfo) -> dt.datetime:
    """'YYYY-MM-DD HH:MM' (market local) or ISO with an offset."""
    t = mc.norm(text).replace("T", " ")
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2}) (\d{1,2}):(\d{2})(?::\d{2})?([+-]\d{2}:?\d{2}|Z)?", t)
    if not m:
        raise Refused(f"start {text!r}: use 'YYYY-MM-DD HH:MM' in the account's market time")
    day = dt.date.fromisoformat(m.group(1))
    if m.group(4):
        return dt.datetime.fromisoformat(f"{m.group(1)}T{int(m.group(2)):02d}:{m.group(3)}:00{m.group(4).replace('Z', '+00:00')}").astimezone(tz)
    return dt.datetime(day.year, day.month, day.day, int(m.group(2)), int(m.group(3)), tzinfo=tz)


def iso(t: dt.datetime) -> str:
    return t.isoformat(timespec="seconds")


def account(root: Path, acc: str) -> mc.Page:
    path = root / "wiki" / "accounts" / f"{acc}.md"
    page = mc.read_page(path, root) if path.is_file() else None
    if not page or not page.meta:
        raise Refused(f"no account page wiki/accounts/{acc}.md")
    return page


def check_owner(user: dict, meta: dict, acc: str) -> str:
    """The rep the appointment belongs to: the owner. Only the owner or the manager may write (rules 6, 16)."""
    owner = mc.norm(meta.get("owner"))
    if mc.norm(user.get("role")) != "manager" and owner != user["id"]:
        raise Refused(f"{acc} is owned by {owner or 'nobody'}, not you (rules 6, 16)")
    return owner or user["id"]


def check_contact(root: Path, contact: str, acc: str, meta: dict) -> None:
    sup = mc.load_suppression(root)  # read once for this booking
    if sup.error:
        raise Refused(f"suppression_state_unavailable: {sup.error}; fix wiki/suppression.csv first (rule 2)")
    domain = mc.norm(meta.get("domain"))
    if domain and sup.match(domain=domain):
        raise Refused(f"{acc}'s domain {domain} is suppressed (rule 2)")
    if not contact:
        return
    path = root / "wiki" / "contacts" / f"{contact}.md"
    page = mc.read_page(path, root) if path.is_file() else None
    if not page or not page.meta or mc.link_id(page.meta.get("account"), "accounts") != acc:
        raise Refused(f"contact {contact} is not on {acc}'s page (rule 5)")
    if mc.norm(page.meta.get("status")) == "do_not_contact":
        raise Refused(f"contact {contact} is do_not_contact (rule 2)")
    email = mc.norm(page.meta.get("email"))
    if email and sup.match(email):
        raise Refused(f"contact {contact} ({email}) is suppressed (rule 2)")


def warnings_for(root: Path, rep: str, market: str, start: dt.datetime, end: dt.datetime, skip: str = "") -> list[str]:
    cfg = mc.market_cfg(root, market)
    out = []
    if start.date() in mc.market_holidays(cfg):
        out.append(f"{start:%a %d %b} is a {market} public holiday")
    if start.weekday() >= 5:
        out.append(f"{start:%a %d %b} is a weekend")
    if start.hour < OPEN_HOURS[0] or end.hour > OPEN_HOURS[1] or (end.hour == OPEN_HOURS[1] and end.minute > 0) or end.date() != start.date():
        out.append(f"{start:%H:%M}–{end:%H:%M} is outside {OPEN_HOURS[0]:02d}:00–{OPEN_HOURS[1]}:00 {market} time")
    if start.date() < mc.today():
        out.append("the date is in the past")
    for b in mc.load_busy(root, rep):
        try:
            b_start, b_end = dt.datetime.fromisoformat(b["start"]), dt.datetime.fromisoformat(b["end"])
        except ValueError:
            continue
        if b_start < end and b_end > start:
            out.append(f"overlaps a busy block in {rep}'s Google Calendar ({b_start.astimezone(start.tzinfo):%H:%M}–{b_end.astimezone(start.tzinfo):%H:%M})")
    for other in mc.load_appointments(root).values():
        if other.get("id") == skip or mc.norm(other.get("rep")) != rep or mc.norm(other.get("status")) not in mc.LIVE_APPOINTMENT:
            continue
        try:
            o_start, o_end = dt.datetime.fromisoformat(other["starts"]), dt.datetime.fromisoformat(other["ends"])
        except (KeyError, ValueError):
            continue
        if o_start < end and o_end > start:
            out.append(f"overlaps {other['id']} ({other.get('account')}, {o_start.astimezone(start.tzinfo):%H:%M}–{o_end.astimezone(start.tzinfo):%H:%M})")
    return out


def new_id(root: Path, acc: str, start: dt.datetime) -> str:
    stem = f"apt-{start:%Y%m%d}-{acc}-"
    taken = {r.get("id") for r in mc.appointment_history(root)}
    n = 1
    while f"{stem}{n}" in taken:
        n += 1
    return f"{stem}{n}"


def write(root: Path, row: dict, user: dict, verb: str, touch: bool) -> None:
    mc.append_csv(root / "log" / "appointments.csv", row, mc.APPOINTMENT_FIELDS)
    if touch:
        mc.append_csv(root / "log" / "touches.csv", {
            "ts": mc.now_stamp(), "rep": row["rep"], "account": row["account"], "contact": row.get("contact", ""),
            "channel": "meeting", "step": "meeting", "pattern": "", "products": "", "status": "meeting_booked",
            "reply_class": "", "ref": row["id"]}, mc.TOUCH_FIELDS)
    start = dt.datetime.fromisoformat(row["starts"])
    abbr = mc.TZ_ABBR.get(row.get("tz", ""), row.get("tz", ""))
    mc.append_log("appointment", user["id"], f"accounts/{row['account']}",
                  f"{verb} {start:%a %d %b %H:%M} {abbr} ({row['status']}) {row['id']}", root)


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------
def add(root: Path, user: dict, a: argparse.Namespace) -> dict:
    page = account(root, a.account)
    meta = page.meta
    rep = check_owner(user, meta, a.account)
    if not mc.is_active(meta):
        raise Refused(f"{a.account} is not active (stage {mc.norm(meta.get('stage'))})")
    contact = mc.norm(a.contact)
    check_contact(root, contact, a.account, meta)
    market = mc.norm(meta.get("market")).upper() or "SG"
    tz_name, tz = mc.market_tz(root, market)
    start = parse_start(a.start, tz)
    end = start + dt.timedelta(minutes=a.minutes)
    if a.minutes <= 0:
        raise Refused("--minutes must be positive")
    status = a.status
    row = {"ts": mc.now_stamp(), "id": new_id(root, a.account, start), "rep": rep, "account": a.account, "contact": contact,
           "kind": a.kind, "title": mc.norm(a.title) or f"{a.kind.replace('_', ' ').title()} · {mc.norm(meta.get('name')) or a.account}",
           "starts": iso(start), "ends": iso(end), "tz": tz_name, "location": mc.norm(a.location), "status": status,
           "source": a.source, "ref": mc.norm(a.ref), "by": user["id"]}
    warns = warnings_for(root, rep, market, start, end)
    if not a.dry_run:
        write(root, row, user, "booked", touch=status == "confirmed")
    return {**row, "market": market, "warnings": warns, "dry_run": a.dry_run}


def change(root: Path, user: dict, a: argparse.Namespace) -> dict:
    cur = mc.load_appointments(root).get(mc.norm(a.id))
    if not cur:
        raise Refused(f"no appointment {a.id}")
    page = account(root, cur["account"])
    check_owner(user, page.meta, cur["account"])
    status = mc.norm(cur.get("status"))
    if status not in mc.LIVE_APPOINTMENT:
        raise Refused(f"{a.id} is already {status}")
    market = mc.norm(page.meta.get("market")).upper() or "SG"
    row = {**{k: cur.get(k, "") for k in mc.APPOINTMENT_FIELDS}, "ts": mc.now_stamp(), "by": user["id"]}
    warns: list[str] = []
    if a.cmd == "reschedule":
        _, tz = mc.market_tz(root, market)
        start = parse_start(a.start, tz)
        old = dt.datetime.fromisoformat(cur["ends"]) - dt.datetime.fromisoformat(cur["starts"])
        end = start + (dt.timedelta(minutes=a.minutes) if a.minutes else old)
        row.update(starts=iso(start), ends=iso(end), status="rescheduled")
        warns = warnings_for(root, row["rep"], market, start, end, skip=row["id"])
        verb, touch = "moved to", False
    else:
        row["status"] = CHANGES[a.cmd]
        if getattr(a, "ref", None):
            row["ref"] = mc.norm(a.ref)
        if a.cmd == "cancel" and getattr(a, "reason", None):
            row["title"] = f"{row['title']} (cancelled: {mc.norm(a.reason)})"
        verb = {"confirm": "confirmed", "cancel": "cancelled", "held": "held", "no-show": "no-show"}[a.cmd]
        touch = a.cmd == "confirm" and status == "tentative"
    if not a.dry_run:
        write(root, row, user, verb, touch=touch)
    return {**row, "market": market, "warnings": warns, "previous": cur.get("status"), "dry_run": a.dry_run}


def listing(root: Path, user: dict, a: argparse.Namespace) -> dict:
    manager = mc.norm(user.get("role")) == "manager"
    want = mc.norm(a.rep) or "me"
    frm, to = mc.to_date(a.date_from), mc.to_date(a.date_to)
    items = []
    for row in mc.load_appointments(root).values():
        rep = mc.norm(row.get("rep"))
        if want == "me" and rep != user["id"]:
            continue
        if want == "all" and not manager and rep != user["id"]:
            continue                                        # rule 16: a rep never sees teammates' appointments
        if want not in ("me", "all") and (rep != want or (not manager and want != user["id"])):
            continue
        day = mc.to_date(row.get("starts", "")[:10])
        if (frm and day and day < frm) or (to and day and day > to):
            continue
        items.append(row)
    items.sort(key=lambda r: r.get("starts", ""))
    return {"rep": want, "items": items}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Book, move and close appointments in log/appointments.csv (ADR-0010).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add", help="book an appointment for an account you own")
    p.add_argument("--account", required=True)
    p.add_argument("--start", required=True, help="'YYYY-MM-DD HH:MM' in the account's market time")
    p.add_argument("--minutes", type=int, default=45)
    p.add_argument("--kind", choices=mc.APPOINTMENT_KINDS, default="meeting")
    p.add_argument("--title", default="")
    p.add_argument("--contact", default="", help="contact id on the account page")
    p.add_argument("--location", default="")
    p.add_argument("--status", choices=("tentative", "confirmed"), default="confirmed")
    p.add_argument("--source", choices=("reply", "rep", "handover", "calendar"), default="rep")
    p.add_argument("--ref", default="", help="the raw/ snapshot that asked for it (e.g. the reply)")
    for name in ("confirm", "cancel", "held", "no-show"):
        q = sub.add_parser(name, help=f"{name} an appointment")
        q.add_argument("id")
        if name == "cancel":
            q.add_argument("--reason", default="")
        if name == "held":
            q.add_argument("--ref", default="")
    r = sub.add_parser("reschedule", help="move an appointment")
    r.add_argument("id")
    r.add_argument("--start", required=True)
    r.add_argument("--minutes", type=int, default=0)
    ls = sub.add_parser("list", help="current appointments (yours; the manager may use --rep all)")
    ls.add_argument("--rep", default="me")
    ls.add_argument("--from", dest="date_from")
    ls.add_argument("--to", dest="date_to")
    for q in (p, r, *[sub.choices[n] for n in ("confirm", "cancel", "held", "no-show")], ls):
        q.add_argument("--json", action="store_true", help="print JSON (the default for this tool)")
        q.add_argument("--dry-run", action="store_true", help="check and print; write nothing")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    user = mc.current_user(root)
    if not user:
        print("Refused: unknown user; run mama-setup first.")
        return 1
    try:
        res = add(root, user, args) if args.cmd == "add" else listing(root, user, args) if args.cmd == "list" else change(root, user, args)
    except Refused as exc:
        print(f"Refused: {exc}")
        return 1
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
