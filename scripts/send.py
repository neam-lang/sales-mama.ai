"""Approve-then-send for Gmail and WhatsApp (ADR-0007, AGENTS.md rules 1 and 14).

Two steps, so a person always sees what goes out before it goes:

    python3 scripts/send.py --preview [--json]
        Read-only. Collects your pending drafts (log/drafts/, channel email or
        whatsapp, not sent yet), reads each Gmail draft LIVE (you may have edited
        it), re-runs every draft_check rule now, and prints a numbered batch.
        Writes log/outbox/<id>.json with a hash of each message.

    python3 scripts/send.py --send <preview-id> --items 1,3 | all [--json]
        Claude Code asks you to approve this exact command (permissions.ask).
        Re-reads each item and refuses it if it changed since the preview, re-runs
        the checks, sends, and logs log/approvals.csv, a `sent` row in
        log/touches.csv, the account's touch history and wiki/log.md.

Hard refusals, whatever the agent says: sending switched off in
knowledge/sending.yaml; the nightly runner (env MAMA_RUNNER); not the account
owner; suppressed email or domain; outside the market's send window or on a
holiday; over the daily quota or the per-run cap; a Gmail draft whose recipient
changed or that gained Cc/Bcc; the connected mailbox is not yours; WhatsApp
without a +E.164 number, recorded consent or (outside the 24 h reply window)
an approved template. A preview expires after 30 minutes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import channels as ch  # noqa: E402
import draft_check as dc  # noqa: E402
import mama_common as mc  # noqa: E402

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

APPROVAL_FIELDS = ("ts", "rep", "preview", "item", "draft", "account", "contact", "channel", "step", "to",
                   "body_sha256", "decision", "detail", "ref")
SEND_CHANNELS = ("email", "whatsapp")
PREVIEW_TTL_MIN = 30
DEFAULT_MAX_PER_RUN = 25


# ----------------------------------------------------------------------------
# Config and gates
# ----------------------------------------------------------------------------
def sending_cfg(root: Path) -> dict:
    data = mc.load_yaml(root / "knowledge" / "sending.yaml", {}) or {}
    return data if isinstance(data, dict) else {}


def global_refusal(root: Path, user: dict | None, cfg: dict) -> str:
    if os.environ.get("MAMA_RUNNER"):
        return "the nightly runner never sends (ADR-0007)"
    if not user:
        return "unknown user: run mama-setup"
    if not cfg.get("enabled"):
        return "sending is switched off (knowledge/sending.yaml `enabled: false`); the manager turns it on"
    return ""


def market_now(mcfg: dict) -> dt.datetime:
    pinned = os.environ.get("MAMA_NOW", "").strip()
    if pinned:
        return dt.datetime.strptime(pinned[:16], "%Y-%m-%d %H:%M")
    tz = ZoneInfo(mc.norm(mcfg.get("tz")) or "UTC") if ZoneInfo else None
    return dt.datetime.now(tz).replace(tzinfo=None)


def window_open_now(mcfg: dict, override) -> tuple[bool, str]:
    days, start, end = dc.parse_window(mcfg, override)
    holidays = {d for d in (mc.to_date(h) for h in mc.as_list(mcfg.get("holidays"))) if d}
    now = market_now(mcfg)
    if now.date() in holidays:
        return False, f"{now:%a %d %b} is a public holiday"
    if not dc.is_send_day(now.date(), days, holidays):
        return False, f"{now:%a} is not a send day ({', '.join(days)})"
    if not (start <= now.time() < end):
        return False, f"{now:%H:%M} is outside {start:%H:%M}–{end:%H:%M}"
    return True, f"open until {end:%H:%M}"


def sent_today(root: Path, me: str) -> int:
    on = mc.today()
    return sum(1 for t in mc.load_touches(root) if t.get("rep") == me and mc.norm(t.get("status")) == "sent"
               and mc.to_date(t.get("ts")) == on)


# ----------------------------------------------------------------------------
# Drafts
# ----------------------------------------------------------------------------
def pending_drafts(root: Path, me: str) -> list[mc.Page]:
    sent = {(t.get("account"), t.get("contact"), t.get("step"), t.get("channel"))
            for t in mc.load_touches(root) if mc.norm(t.get("status")) == "sent"}
    out = []
    folder = root / "log" / "drafts"
    for p in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        page = mc.read_page(p, root)
        m = page.meta if page else None
        if not m or mc.norm(m.get("rep")) != me or mc.norm(m.get("channel")) not in SEND_CHANNELS:
            continue
        if mc.norm(m.get("sent_ref")):
            continue
        key = (mc.norm(m.get("account")), mc.norm(m.get("contact")), mc.norm(m.get("step")), mc.norm(m.get("channel")))
        if key in sent:
            continue
        out.append(page)
    return out


def live_message(root: Path, page: mc.Page, token: str) -> dict:
    """What would actually go out: the live Gmail draft, or the saved WhatsApp text."""
    m = page.meta
    if mc.norm(m.get("channel")) == "whatsapp":
        return {"to": mc.norm(m.get("to")), "subject": "", "body": page.body, "cc": "", "bcc": "",
                "template": mc.norm(m.get("wa_template")), "params": [str(x) for x in mc.as_list(m.get("wa_params"))],
                "lang": mc.norm(m.get("wa_lang")) or "en", "draft": None}
    ref = mc.norm(m.get("ref"))
    if ref and ref != "pending-mailbox":
        d = ch.gmail_get_draft(root, ref, page.path, token=token)
        return {"to": d["to"], "subject": d["subject"], "body": d["body"], "cc": d.get("cc", ""),
                "bcc": d.get("bcc", ""), "draft": d}
    return {"to": mc.norm(m.get("to")), "subject": mc.norm(m.get("subject")), "body": page.body, "cc": "", "bcc": "",
            "draft": None}


def msg_hash(msg: dict) -> str:
    return ch.body_hash(msg.get("to", ""), msg.get("subject", ""), msg.get("body", ""), msg.get("template", ""),
                        "|".join(msg.get("params") or []))


def evaluate(root: Path, user: dict, cfg: dict, page: mc.Page, msg: dict, mailbox: str) -> list[dict]:
    """All checks for one item; each {check, ok, detail}."""
    m = page.meta
    channel = mc.norm(m.get("channel"))
    res, info = dc.run_checks(
        root, account_id=mc.norm(m.get("account")), contact_id=mc.norm(m.get("contact")), step=mc.norm(m.get("step")),
        channel=channel, pattern_id=mc.norm(m.get("pattern")), products=[str(p) for p in mc.as_list(m.get("products"))],
        subject=msg.get("subject", ""), body=msg.get("body", ""), user=user,
        wa_template=mc.norm(m.get("wa_key")) if mc.norm(m.get("wa_template")) else "",
        wa_params=msg.get("params") or [])
    checks = list(res.checks)
    chans = cfg.get("channels") or {}
    checks.append({"check": "channel_on", "ok": bool(chans.get(channel, True)),
                   "detail": f"{channel} {'on' if chans.get(channel, True) else 'off'} in knowledge/sending.yaml"})
    mcfg = dc.load_market(root, info.get("market", ""))
    ok, why = window_open_now(mcfg, user.get("send_window_override"))
    checks.append({"check": "window_now", "ok": ok, "detail": why})
    if channel == "email":
        want = (info.get("email") or "").lower()
        got = [a.strip().lower() for a in re.findall(r"[\w.+'-]+@[\w.-]+", msg.get("to", ""))]
        checks.append({"check": "recipient", "ok": got == [want] and not msg.get("cc") and not msg.get("bcc"),
                       "detail": f"to {', '.join(got) or '(none)'}" + (" + Cc/Bcc" if msg.get("cc") or msg.get("bcc") else "")
                       + ("" if got == [want] else f"; the contact is {want}")})
        me_email = mc.norm(user.get("email")).lower()
        checks.append({"check": "mailbox", "ok": bool(mailbox) and mailbox.lower() == me_email,
                       "detail": f"sending from {mailbox or '(not connected)'}; your profile is {me_email}"})
    elif channel == "whatsapp":
        checks.append({"check": "recipient", "ok": msg.get("to") == info.get("wa_number"),
                       "detail": f"to {msg.get('to')}; contact number {info.get('wa_number')}"})
    return checks


# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
def log_approval(root: Path, row: dict) -> None:
    mc.append_csv(root / "log" / "approvals.csv", {k: row.get(k, "") for k in APPROVAL_FIELDS}, APPROVAL_FIELDS)


def record_sent(root: Path, user: dict, page: mc.Page, ref: str) -> None:
    m = page.meta
    acc, step, channel = mc.norm(m.get("account")), mc.norm(m.get("step")), mc.norm(m.get("channel"))
    mc.append_csv(root / "log" / "touches.csv", {
        "ts": mc.now_stamp(), "rep": user["id"], "account": acc, "contact": mc.norm(m.get("contact")),
        "channel": channel, "step": step, "pattern": mc.norm(m.get("pattern")),
        "products": ";".join(str(p) for p in mc.as_list(m.get("products"))), "status": "sent",
        "reply_class": "", "ref": ref}, mc.TOUCH_FIELDS)
    mc.update_frontmatter(page.path, {"sent_ref": ref, "sent_at": mc.now_stamp()})
    acc_path = root / "wiki" / "accounts" / f"{acc}.md"
    account = mc.read_page(acc_path, root)
    if account and account.meta:
        changes = {"last_touch": mc.today().isoformat(), "updated": mc.today().isoformat()}
        if mc.norm(account.meta.get("stage")) in ("new", "researched"):
            changes["stage"] = "contacted"
        mc.update_frontmatter(acc_path, changes)
        _append_touch_line(acc_path, f"- {mc.today().isoformat()} · {step} · {channel} · "
                                     f"{mc.norm(m.get('pattern')) or '-'} · sent ({ref})")
    mc.append_log("send", user["id"], f"accounts/{acc}", f"{step} {channel} sent after approval ({ref})", root)


def _append_touch_line(path: Path, line: str) -> None:
    text = mc.read_text(path)
    lines = text.splitlines()
    try:
        i = next(k for k, ln in enumerate(lines) if ln.strip().lower() == "## touch history")
    except StopIteration:
        mc.write_text(path, text.rstrip("\n") + "\n## Touch history\n" + line + "\n")
        return
    j = i + 1
    while j < len(lines) and not lines[j].startswith("## "):
        j += 1
    while j > i + 1 and not lines[j - 1].strip():
        j -= 1
    lines.insert(j, line)
    mc.write_text(path, "\n".join(lines) + "\n")


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------
def _connections(need_email: bool) -> tuple[str, str]:
    """(gmail access token, mailbox address); empty when not needed or not connected."""
    if not need_email:
        return "", ""
    st = ch.gmail_status()
    if ch.fake():
        return "", st.get("email", "")
    if not st["ok"]:
        return "", ""
    token = ch.gmail_access_token()
    return token, ch.gmail_profile(token).get("emailAddress", "")


def preview(root: Path, user: dict, cfg: dict) -> dict:
    me = user["id"]
    drafts = pending_drafts(root, me)
    token, mailbox = _connections(any(mc.norm(p.meta.get("channel")) == "email" for p in drafts))
    items = []
    for n, page in enumerate(drafts, 1):
        m = page.meta
        try:
            msg = live_message(root, page, token)
            checks = evaluate(root, user, cfg, page, msg, mailbox)
        except ch.ChannelError as exc:
            msg, checks = {"to": mc.norm(m.get("to")), "subject": mc.norm(m.get("subject")), "body": ""}, \
                [{"check": "fetch", "ok": False, "detail": str(exc)}]
        items.append({"n": n, "draft": mc.rel_posix(page.path, root), "account": mc.norm(m.get("account")),
                      "contact": mc.norm(m.get("contact")), "channel": mc.norm(m.get("channel")),
                      "step": mc.norm(m.get("step")), "to": msg.get("to", ""), "subject": msg.get("subject", ""),
                      "template": msg.get("template", ""), "body": msg.get("body", ""),
                      "body_sha256": msg_hash(msg), "ok": all(c["ok"] for c in checks),
                      "problems": [f"{c['check']}: {c['detail']}" for c in checks if not c["ok"]]})
    pid = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{me}"
    out = {"id": pid, "rep": me, "created": mc.now_stamp(), "sending_enabled": bool(cfg.get("enabled")),
           "quota_left": _quota_left(root, user), "items": items}
    folder = root / "log" / "outbox"
    folder.mkdir(parents=True, exist_ok=True)
    mc.write_text(folder / f"{pid}.json", json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    out["file"] = mc.rel_posix(folder / f"{pid}.json", root)
    return out


def _quota_left(root: Path, user: dict) -> int | None:
    try:
        return max(int(user.get("daily_quota")) - sent_today(root, user["id"]), 0)
    except (TypeError, ValueError):
        return None


def send(root: Path, user: dict, cfg: dict, pid: str, which: str) -> dict:
    me = user["id"]
    path = root / "log" / "outbox" / f"{pid}.json"
    if not path.is_file():
        return {"ok": False, "error": f"no preview {pid}: run --preview first"}
    prev = json.loads(mc.read_text(path))
    if prev.get("rep") != me:
        return {"ok": False, "error": f"preview {pid} belongs to {prev.get('rep')}"}
    created = dt.datetime.strptime(prev["created"], "%Y-%m-%d %H:%M")
    if dt.datetime.strptime(mc.now_stamp(), "%Y-%m-%d %H:%M") - created > dt.timedelta(minutes=PREVIEW_TTL_MIN):
        return {"ok": False, "error": f"preview {pid} is older than {PREVIEW_TTL_MIN} minutes: run --preview again"}
    by_n = {it["n"]: it for it in prev.get("items", [])}
    wanted = sorted(by_n) if which.strip().lower() == "all" else \
        sorted({int(x) for x in re.findall(r"\d+", which)})
    unknown = [n for n in wanted if n not in by_n]
    if unknown or not wanted:
        return {"ok": False, "error": f"items {unknown or which} are not in preview {pid}"}
    cap = int(cfg.get("max_per_run") or DEFAULT_MAX_PER_RUN)
    if len(wanted) > cap:
        return {"ok": False, "error": f"{len(wanted)} items is more than max_per_run {cap} (knowledge/sending.yaml)"}
    left = _quota_left(root, user)
    if left is not None and len(wanted) > left:
        return {"ok": False, "error": f"{len(wanted)} items but only {left} left in today's quota"}

    need_email = any(by_n[n]["channel"] == "email" for n in wanted)
    try:
        token, mailbox = _connections(need_email)
    except ch.ChannelError as exc:
        return {"ok": False, "error": str(exc)}
    results = []
    for n in wanted:
        it = by_n[n]
        row = {"ts": mc.now_stamp(), "rep": me, "preview": pid, "item": n, "draft": it["draft"],
               "account": it["account"], "contact": it["contact"], "channel": it["channel"], "step": it["step"],
               "to": it["to"], "body_sha256": it["body_sha256"]}
        page = mc.read_page(root / it["draft"], root)
        try:
            if not page or not page.meta:
                raise ch.ChannelError("draft file missing")
            if mc.norm(page.meta.get("sent_ref")):
                raise ch.ChannelError(f"already sent ({page.meta.get('sent_ref')})")
            msg = live_message(root, page, token)
            if msg_hash(msg) != it["body_sha256"]:
                raise ch.ChannelError("changed since the preview: run --preview again and re-approve")
            failed = [f"{c['check']}: {c['detail']}" for c in evaluate(root, user, cfg, page, msg, mailbox) if not c["ok"]]
            if failed:
                log_approval(root, {**row, "decision": "refused", "detail": "; ".join(failed)})
                results.append({"n": n, "status": "refused", "detail": failed})
                continue
            if it["channel"] == "email":
                draft = msg["draft"]
                if draft is None:  # no mailbox draft yet: create it from the saved text, then send that
                    did = ch.gmail_create_draft(root, sender=mailbox, to=msg["to"], subject=msg["subject"],
                                                body=msg["body"], token=token, draft_file=page.path)
                    draft = ch.gmail_get_draft(root, did, page.path, token=token)
                ref = "gmail:" + ch.gmail_send_draft(draft, unsubscribe_to=mailbox, token=token)
            else:
                ref = "wa:" + ch.whatsapp_send(to=msg["to"], template=msg.get("template", ""),
                                               lang=msg.get("lang", "en"), params=msg.get("params"),
                                               text="" if msg.get("template") else msg["body"])
        except ch.ChannelError as exc:
            log_approval(root, {**row, "decision": "error" if "changed" not in str(exc) else "refused",
                                "detail": str(exc)})
            results.append({"n": n, "status": "refused" if "changed" in str(exc) or "already" in str(exc)
                            else "error", "detail": [str(exc)]})
            continue
        log_approval(root, {**row, "decision": "sent", "detail": "approved by the rep", "ref": ref})
        record_sent(root, user, page, ref)
        results.append({"n": n, "status": "sent", "ref": ref, "account": it["account"], "channel": it["channel"]})
    return {"ok": all(r["status"] == "sent" for r in results), "preview": pid, "results": results}


def _print_preview(p: dict) -> None:
    print(f"Preview {p['id']} · sending {'on' if p['sending_enabled'] else 'OFF'} · "
          f"quota left today: {p['quota_left'] if p['quota_left'] is not None else '-'}")
    if not p["items"]:
        print("Nothing pending: no unsent email or WhatsApp drafts of yours in log/drafts/.")
    for it in p["items"]:
        head = f"[{it['n']}] {'READY' if it['ok'] else 'BLOCKED'} · {it['channel']} · {it['account']} · {it['step']} · to {it['to']}"
        print("\n" + head)
        if it.get("subject"):
            print(f"    Subject: {it['subject']}")
        if it.get("template"):
            print(f"    Template: {it['template']}")
        for line in (it.get("body") or "").strip().splitlines():
            print(f"    | {line}")
        for prob in it["problems"]:
            print(f"    ! {prob}")
    ready = [str(i["n"]) for i in p["items"] if i["ok"]]
    if ready:
        print(f"\nTo send, approve: python3 scripts/send.py --send {p['id']} --items {','.join(ready)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Approve-then-send for Gmail and WhatsApp (ADR-0007): preview a "
                                             "batch, then send the items the rep approved.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--preview", action="store_true", help="read-only: list pending drafts with all checks")
    g.add_argument("--send", metavar="PREVIEW_ID", help="send approved items from that preview")
    ap.add_argument("--items", default="", help="with --send: item numbers (1,3) or 'all'")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    user = mc.current_user(root)
    cfg = sending_cfg(root)
    if args.preview:
        if not user:
            print("unknown user: run mama-setup")
            return 1
        p = preview(root, user, cfg)
        print(json.dumps(p, indent=2, ensure_ascii=False)) if args.json else _print_preview(p)
        return 0
    refusal = global_refusal(root, user, cfg)
    if refusal:
        out = {"ok": False, "error": refusal}
    elif not args.items:
        out = {"ok": False, "error": "--items is required with --send (e.g. --items 1,3 or --items all)"}
    else:
        out = send(root, user, cfg, args.send, args.items)
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    elif out.get("error"):
        print(f"Not sent: {out['error']}")
    else:
        for r in out["results"]:
            print(f"[{r['n']}] {r['status']}" + (f" · {r['ref']}" if r.get("ref") else "")
                  + ("" if r["status"] == "sent" else " · " + "; ".join(r["detail"])))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
