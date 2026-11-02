"""Pre-draft checks for mama-draft (AGENTS.md rules 1-7, 13, 14; playbook Message rules).

Run it on the draft text BEFORE creating a mailbox draft. Every check must pass;
the JSON lists each one with a reason. With --save (and all checks passing) the
draft and its metadata go to log/drafts/<date>-<account>-<step>.md so eval.py
can audit drafts offline (send window, language, catalog, fabrication).

Checks: owner, suppression (contact email AND domain), contact/account status,
stage vs step, contract_ending timing, channel and opt-in, language, pattern
(approved, step, market, lang), products in catalog, words <= 120, one
unsubscribe line, signature, <ADV> policy, links, and the entity check
(every name, number and date must appear on the account/contact page, in
knowledge/ or in the rep's profile). WhatsApp (ADR-0007) adds: +E.164 number,
recorded consent (whatsapp_opt_in + date + raw/ source) and, outside the 24 h
window after the contact's last WhatsApp reply, an approved template from
knowledge/whatsapp_templates.yaml (the body is rendered from it).

    python3 scripts/draft_check.py --account kestrel-physio --contact marcus-teo-kestrel-physio \\
        --step first --pattern first-hiring-it-stretch --products it-care \\
        --subject "Your IT & Systems hire" --file draft.txt --save
    python3 scripts/draft_check.py --account kestrel-physio --contact marcus-teo-kestrel-physio \\
        --step first --channel whatsapp --pattern first-hiring-it-stretch --products it-care \\
        --wa-template first-hiring-it-stretch-wa --wa-params "Marcus|IT & Systems Executive" --save
    python3 scripts/draft_check.py --next-window --market SG
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
import mama_common as mc  # noqa: E402

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

STEPS = ("connect", "first", "fu1", "fu2", "fu3", "reply")
SEQ_STEPS = ("connect", "first", "fu1", "fu2", "fu3")
CHANNELS = ("email", "linkedin", "whatsapp", "phone")
MAX_WORDS = 120
LINKEDIN_MAX = 300
ADV_BULK = 10
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
WA_WINDOW_HOURS = 24
PLACEHOLDER_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")
UNSUB_RE = re.compile(r"unsubscribe|opt out|opt-out|reply\s+\W?stop\W?|no longer wish", re.I)
URL_RE = re.compile(r"\b(?:https?://|www\.)[^\s>)]+", re.I)
WORD_RE = re.compile(r"[A-Za-z0-9][\w'’&.-]*")
# Capitalised runs ("Allied Health Expo", "Marcus", "IT Care"); joined by spaces, & or '-'.
CAP_RUN_RE = re.compile(r"\b[A-Z][\w'’&-]*(?:[ \t]+(?:&[ \t]+)?[A-Z][\w'’&-]*)*")
NUM_RE = re.compile(r"(?<![\w-])(?:S\$|RM|₹|SGD|MYR|INR)?\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:%|k|m|million|bn))?",
                    re.I)
DATE_DM_RE = re.compile(r"\b(\d{1,2})(?:\s*[–-]\s*\d{1,2})?\s+(" + "|".join(MONTHS) + r")[a-z]*\.?(?:\s+(\d{4}))?",
                        re.I)
DATE_MD_RE = re.compile(r"\b(" + "|".join(MONTHS) + r")[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(\d{4}))?",
                        re.I)
# Capitalised words that are never entities (greetings, pronouns, sentence glue).
COMMON = set("""
a an and are as at be best but by can cheers could dear do does for from good happy have hello
hey hi how i if in is it its just kind let many may might more most no not of on or our please
quick regards so thank thanks that the their there these they this those to totally us warm we
what when where which while who why will with would yes you your yours congratulations
congrats sincerely ps re fyi worth saw noticed reading shall should until when once also
""".split())
WEEKDAYS_FULL = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                 "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun"}
MONTH_WORDS = {"january", "february", "march", "april", "june", "july", "august", "september",
               "october", "november", "december", *MONTHS}


class Result:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def add(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append({"check": name, "ok": bool(ok), "detail": detail})
        return ok

    @property
    def ok(self) -> bool:
        return all(c["ok"] for c in self.checks)


# ----------------------------------------------------------------------------
# Knowledge helpers
# ----------------------------------------------------------------------------
def load_market(root: Path, market: str) -> dict:
    data = mc.load_yaml(root / "knowledge" / "markets.yaml", {}) or {}
    markets = data.get("markets", data) if isinstance(data, dict) else {}
    return (markets or {}).get(market) or {}


def load_products(root: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    folder = root / "knowledge" / "products"
    for p in sorted(folder.glob("*.y*ml")) if folder.is_dir() else []:
        data = mc.load_yaml(p, {}) or {}
        if isinstance(data, dict):
            out[mc.norm(data.get("id")) or p.stem] = data
    return out


def find_pattern(root: Path, pid: str) -> mc.Page | None:
    folder = root / "wiki" / "responses" / "patterns"
    p = folder / f"{pid}.md"
    if p.is_file():
        return mc.read_page(p, root)
    for page in mc.iter_pages("pattern", root):
        if page.id == pid:
            return page
    return None


def load_wa_templates(root: Path) -> dict[str, dict]:
    data = mc.load_yaml(root / "knowledge" / "whatsapp_templates.yaml", {}) or {}
    tpl = data.get("templates") if isinstance(data, dict) else None
    return {str(k): (v or {}) for k, v in tpl.items()} if isinstance(tpl, dict) else {}


def render_template(text: str, params: list[str]) -> str:
    return PLACEHOLDER_RE.sub(lambda m: params[int(m.group(1)) - 1] if 0 < int(m.group(1)) <= len(params)
                              else m.group(0), text)


def now_local() -> dt.datetime:
    """Local wall-clock time; env MAMA_NOW ('YYYY-MM-DD HH:MM') pins it for tests."""
    pinned = os.environ.get("MAMA_NOW", "").strip()
    if pinned:
        return dt.datetime.strptime(pinned[:16], "%Y-%m-%d %H:%M")
    return dt.datetime.now()


def wa_number(cmeta: dict) -> str:
    return re.sub(r"[\s()-]", "", mc.norm(cmeta.get("whatsapp")) or mc.norm(cmeta.get("phone")))


def wa_window_open(touches: list[dict], contact_id: str, now: dt.datetime | None = None) -> bool:
    """True within 24 h of the contact's last WhatsApp reply (free text allowed; otherwise a template)."""
    now = now or now_local()
    for t in touches:
        if t.get("channel") == "whatsapp" and t.get("step") == "reply" and t.get("contact") == contact_id:
            try:
                ts = dt.datetime.strptime(mc.norm(t.get("ts"))[:16], "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            if dt.timedelta(0) <= now - ts <= dt.timedelta(hours=WA_WINDOW_HOURS):
                return True
    return False


def consent_problems(root: Path, cmeta: dict) -> list[str]:
    out = []
    if cmeta.get("whatsapp_opt_in") is not True:
        out.append("whatsapp_opt_in is not true")
    if not mc.to_date(cmeta.get("whatsapp_opt_in_date")):
        out.append("no whatsapp_opt_in_date")
    src = mc.norm(cmeta.get("whatsapp_opt_in_source"))
    if not src.startswith("raw/") or not (root / src.split("#")[0]).is_file():
        out.append("whatsapp_opt_in_source must be an existing raw/ file")
    return out


def suppression_hit(root: Path, email: str) -> str:
    """The suppression row value that blocks `email` (email or its domain), else ''."""
    email = email.strip().lower()
    domain = email.split("@", 1)[1] if "@" in email else ""
    for row in mc.read_csv(root / "wiki" / "suppression.csv"):
        value = mc.norm(row.get("value")).lower()
        kind = mc.norm(row.get("type")).lower() or ("domain" if "@" not in value else "email")
        if not value:
            continue
        if kind == "email" and value == email:
            return value
        if kind == "domain" and domain and (domain == value.lstrip("@") or domain.endswith("." + value.lstrip("@"))):
            return value
    return ""


# ----------------------------------------------------------------------------
# Send window
# ----------------------------------------------------------------------------
def parse_window(market_cfg: dict, override) -> tuple[list[str], dt.time, dt.time]:
    win = override if isinstance(override, dict) and override else (market_cfg.get("send_windows") or {})
    days = [mc.norm(d).lower()[:3] for d in mc.as_list(win.get("days"))] or ["mon", "tue", "wed", "thu"]
    hours = mc.norm(win.get("hours")) or "09:00-11:30"
    a, _, b = hours.replace("–", "-").partition("-")
    start = dt.time.fromisoformat(a.strip().zfill(5))
    end = dt.time.fromisoformat(b.strip().zfill(5))
    return days, start, end


def is_send_day(day: dt.date, days: list[str], holidays: set[dt.date]) -> bool:
    return DAYS[day.weekday()] in days and day not in holidays


def next_window(market_cfg: dict, override=None, now: dt.datetime | None = None) -> dict:
    """Next send slot in the market's time zone, skipping holidays."""
    tzname = mc.norm(market_cfg.get("tz")) or "UTC"
    tz = ZoneInfo(tzname) if ZoneInfo else None
    if now is None:
        now = dt.datetime.now(tz) if tz else dt.datetime.now()
        if mc.today() != now.date():  # MAMA_TODAY pins tests to a date, before the window
            now = dt.datetime.combine(mc.today(), dt.time(0, 0), tzinfo=tz)
    days, start, end = parse_window(market_cfg, override)
    holidays = {d for d in (mc.to_date(h) for h in mc.as_list(market_cfg.get("holidays"))) if d}
    day = now.date()
    for _ in range(60):
        if is_send_day(day, days, holidays) and (day > now.date() or now.time() < end):
            begin = start if day > now.date() or now.time() < start else now.time().replace(second=0, microsecond=0)
            abbr = (dt.datetime.combine(day, begin, tzinfo=tz).tzname() if tz else "") or tzname
            if abbr.startswith(("+", "-")):
                abbr = {"Asia/Singapore": "SGT", "Asia/Kuala_Lumpur": "MYT", "Asia/Kolkata": "IST"}.get(tzname, tzname)
            label = f"{day.strftime('%a')} {day.day} {day.strftime('%b')}, {begin:%H:%M}–{end:%H:%M} {abbr}"
            return {"date": day.isoformat(), "start": f"{begin:%H:%M}", "end": f"{end:%H:%M}", "tz": tzname,
                    "label": label}
        day += dt.timedelta(days=1)
    return {}


def window_ok(market_cfg: dict, override, date_str: str) -> bool:
    d = mc.to_date(date_str)
    if not d:
        return False
    days, _, _ = parse_window(market_cfg, override)
    holidays = {h for h in (mc.to_date(x) for x in mc.as_list(market_cfg.get("holidays"))) if h}
    return is_send_day(d, days, holidays)


# ----------------------------------------------------------------------------
# Entity check (rule 5)
# ----------------------------------------------------------------------------
def source_corpus(root: Path, account: mc.Page, contacts: list[mc.Page], rep: dict | None) -> str:
    parts = [account.text] + [c.text for c in contacts]
    for p in sorted((root / "knowledge").rglob("*")):
        if p.is_file() and p.suffix in (".md", ".yaml", ".yml"):
            parts.append(mc.read_text(p))
    if rep and rep.get("_path") and (root / rep["_path"]).is_file():
        parts.append(mc.read_text(root / rep["_path"]))
    return "\n".join(parts)


def _norm_text(text: str) -> str:
    t = text.replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", t).lower()


def _digits(s: str) -> str:
    return re.sub(r"[^\d.]", "", s).strip(".")


def _iso_days(corpus: str) -> set[tuple[int, int]]:
    return {(int(m), int(d)) for _, m, d in re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", corpus)}


def strip_boilerplate(body: str, rep: dict | None) -> str:
    """Body without the signature block and the unsubscribe line (they are checked separately)."""
    sig = [ln.strip() for ln in mc.norm((rep or {}).get("signature")).splitlines() if ln.strip()]
    keep = []
    for line in body.splitlines():
        s = line.strip()
        if s in sig or UNSUB_RE.search(s):
            continue
        keep.append(line)
    return "\n".join(keep)


def entity_problems(text: str, corpus: str) -> list[str]:
    """Names, numbers and dates in `text` that `corpus` doesn't contain."""
    cnorm = _norm_text(corpus)
    cdigits = _norm_text(corpus).replace(",", "")
    iso = _iso_days(corpus)
    bad: list[str] = []
    seen: set[str] = set()

    # Dates first, then blank them out so their numbers aren't re-checked.
    work = text
    for rx, order in ((DATE_DM_RE, "dm"), (DATE_MD_RE, "md")):
        for m in list(rx.finditer(work)):
            day, mon_s, year = (m.group(1), m.group(2), m.group(3)) if order == "dm" else (m.group(2), m.group(1), m.group(3))
            mon = MONTHS[mon_s.lower()[:3]]
            raw = m.group(0).rstrip(".")
            if (mon, int(day)) in iso or _norm_text(raw) in cnorm:
                pass
            elif raw not in seen:
                seen.add(raw)
                bad.append(f"date \"{raw}\"")
        work = rx.sub(" ", work)

    for m in NUM_RE.finditer(work):
        raw = m.group(0).strip()
        digits = _digits(raw)
        if not digits or raw in seen:
            continue
        seen.add(raw)
        if digits not in cdigits and _norm_text(raw) not in cnorm:
            bad.append(f"number \"{raw}\"")

    for sent in re.split(r"(?<=[.!?:])\s+|\n+", work):
        runs = list(CAP_RUN_RE.finditer(sent))
        for i, m in enumerate(runs):
            words = m.group(0).split()
            # Drop leading glue words ("Hi Marcus" -> "Marcus"; sentence-initial "We").
            while words and (words[0].lower().strip("'’") in COMMON or
                             (m.start() == 0 and len(words) == 1 and words[0].lower() in COMMON)):
                words = words[1:]
            words = [w for w in words if w.lower() not in WEEKDAYS_FULL and w.lower() not in MONTH_WORDS]
            if not words:
                continue
            phrase = " ".join(words).strip("'’&-")
            if not phrase or phrase in seen:
                continue
            if m.start() == 0 and len(words) == 1 and phrase.lower() in COMMON:
                continue
            seen.add(phrase)
            if _norm_text(phrase) in cnorm:
                continue
            # A multi-word run is fine if each word is a known name piece (e.g. "Marcus" + "IT").
            if len(words) > 1 and all(_norm_text(w) in cnorm for w in words):
                continue
            # Sentence-initial ordinary word ("Opening", "Booth"): fine if it's lowercase in the corpus.
            if m.start() == 0 and len(words) == 1 and re.search(r"\b" + re.escape(phrase.lower()) + r"\b", cnorm):
                continue
            bad.append(f"name \"{phrase}\"")
    return bad


# ----------------------------------------------------------------------------
# Main check
# ----------------------------------------------------------------------------
def run_checks(root: Path, *, account_id: str, contact_id: str, step: str, channel: str, pattern_id: str,
               products: list[str], subject: str, body: str, user: dict | None,
               override_step_rules: bool = False, wa_template: str = "",
               wa_params: list[str] | None = None) -> tuple[Result, dict]:
    r = Result()
    info: dict = {}
    if not r.add("user", user is not None, "" if user else "unknown user: run mama-setup"):
        return r, info
    me = mc.norm(user.get("id"))
    acc_path = root / "wiki" / "accounts" / f"{account_id}.md"
    account = mc.read_page(acc_path, root) if acc_path.is_file() else None
    if not r.add("account", account is not None and account.meta is not None, f"wiki/accounts/{account_id}.md"):
        return r, info
    meta = account.meta
    market = mc.norm(meta.get("market"))
    mcfg = load_market(root, market)
    info.update(market=market)

    owner = mc.norm(meta.get("owner"))
    r.add("owner", owner == me, f"owner `{owner or '(none)'}`, you are `{me}`")

    con_path = root / "wiki" / "contacts" / f"{contact_id}.md"
    contact = mc.read_page(con_path, root) if con_path.is_file() else None
    if not r.add("contact", contact is not None and contact.meta is not None and
                 mc.link_id(contact.meta.get("account")) == account_id,
                 f"wiki/contacts/{contact_id}.md must exist and belong to {account_id}"):
        return r, info
    cmeta = contact.meta
    email = mc.norm(cmeta.get("email"))
    lang = mc.norm(cmeta.get("lang")) or "en"
    info.update(email=email, lang=lang)

    # Suppression (rule 2) and status.
    hit = suppression_hit(root, email) if email else ""
    acc_domain = mc.norm(meta.get("domain")).lower()
    if not hit and acc_domain:
        hit = suppression_hit(root, f"x@{acc_domain}")
    r.add("suppression", not hit, f"suppressed: {hit}" if hit else f"{email or '(no email)'} and domain clear")
    cst, ast = mc.norm(cmeta.get("status")) or "active", mc.norm(meta.get("stage"))
    r.add("status", cst == "active" and ast != "do_not_contact",
          f"contact status `{cst}`, account stage `{ast}`")

    # Stage vs step.
    touches = [t for t in mc.load_touches(root) if t.get("account") == account_id]
    stage_ok, why = True, ""
    if ast in ("handed_over", "closed_lost", "do_not_contact"):
        stage_ok, why = False, f"no drafts at stage `{ast}`"
    elif step in ("connect", "first"):
        stage_ok = ast in ("new", "researched") or (ast == "nurture" and override_step_rules)
        why = f"`{step}` needs stage new/researched (is `{ast}`)"
        if stage_ok and step == "first":
            rec = mc.as_list(meta.get("recommended"))
            has_rec = bool(rec) and bool(mc.section(account.body, "Recommendation"))
            stage_ok, why = has_rec, "first needs `recommended:` and a ## Recommendation" if not has_rec else ""
    elif step in ("fu1", "fu2", "fu3"):
        prev = {"fu1": "first", "fu2": "fu1", "fu3": "fu2"}[step]
        sent = [t for t in touches if t.get("step") == prev and t.get("status") == "sent"]
        replied = [t for t in touches if t.get("step") == "reply" and sent and t.get("ts", "") > sent[-1].get("ts", "")]
        stage_ok = ast == "contacted" and bool(sent) and not replied
        why = f"`{step}` needs stage contacted, `{prev}` sent and no reply since"
    elif step == "reply":
        stage_ok, why = ast in ("replied", "meeting"), f"`reply` needs stage replied/meeting (is `{ast}`)"
    r.add("stage", stage_ok, why if not stage_ok else f"stage `{ast}` allows `{step}`")

    # contract_ending timing (playbook: first email 90-60 days before contract_end, not earlier).
    if step in ("connect", "first") and "contract_ending" in [str(s) for s in mc.as_list(meta.get("signals"))]:
        ce = mc.to_date(meta.get("contract_end"))
        opens = ce - dt.timedelta(days=90) if ce else None
        r.add("contract_timing", opens is None or mc.today() >= opens,
              f"contract_end {ce}: first email not before {opens}" if opens else "no contract_end")

    # Channel (rule 14).
    allowed = [mc.norm(c) for c in mc.as_list(mcfg.get("channels"))] or ["email"]
    ch_ok = channel in allowed
    detail = f"{channel} {'allowed' if ch_ok else 'not allowed'} in {market} ({', '.join(allowed)})"
    if ch_ok and channel in ("whatsapp", "phone"):
        engaged = any(t.get("step") == "reply" and t.get("contact") in (contact_id, email) for t in touches)
        ch_ok = bool(cmeta.get("whatsapp_opt_in")) or engaged
        detail += "" if ch_ok else "; contact has not opted in or replied"
    if ch_ok and channel == "email":
        ch_ok = bool(email)
        detail += "" if ch_ok else "; contact has no email"
    r.add("channel", ch_ok, detail)

    # WhatsApp (ADR-0007): number, recorded consent, template outside the 24 h window.
    if channel == "whatsapp":
        number = wa_number(cmeta)
        info["wa_number"] = number
        r.add("wa_number", bool(E164_RE.match(number)), number or "no `whatsapp:` or `phone:` on the contact"
              + ("" if E164_RE.match(number) else " (needs +E.164, e.g. +6591234567)"))
        cp = consent_problems(root, cmeta)
        r.add("consent", not cp, "; ".join(cp) or f"opted in {cmeta.get('whatsapp_opt_in_date')} "
                                                  f"({cmeta.get('whatsapp_opt_in_source')})")
        window = wa_window_open(touches, contact_id)
        info["wa_window_open"] = window
        if wa_template or not window:
            tpl = load_wa_templates(root).get(wa_template) if wa_template else None
            params = wa_params or []
            problems = []
            if not tpl:
                problems.append(f"template `{wa_template or '(none)'}` not in knowledge/whatsapp_templates.yaml"
                                + ("" if wa_template else " (needed outside the 24 h reply window)"))
            else:
                text = mc.norm(tpl.get("text"))
                need = max([int(n) for n in PLACEHOLDER_RE.findall(text)] or [0])
                if not mc.norm(tpl.get("name")):
                    problems.append("no Meta template `name`")
                if market not in [mc.norm(m) for m in mc.as_list(tpl.get("markets"))]:
                    problems.append(f"markets {tpl.get('markets')} lack {market}")
                if step not in [mc.norm(x) for x in mc.as_list(tpl.get("steps"))]:
                    problems.append(f"steps {tpl.get('steps')} lack {step}")
                if (mc.norm(tpl.get("lang")) or "en") != lang:
                    problems.append(f"template lang `{tpl.get('lang')}` ≠ contact lang `{lang}`")
                tsig = [mc.norm(x) for x in mc.as_list(tpl.get("signals"))]
                asig = [mc.norm(x) for x in mc.as_list(meta.get("signals"))]
                if tsig and not set(tsig) & set(asig):
                    problems.append(f"template states {tsig}, but the account's signals are {asig or 'none'}")
                if len(params) != need:
                    problems.append(f"{len(params)} parameter(s) given, template needs {need}")
                if not UNSUB_RE.search(text):
                    problems.append("template text has no opt-out line (e.g. \"Reply STOP to opt out\")")
                if not problems:
                    body = render_template(text, params)
                    info.update(wa_template=mc.norm(tpl.get("name")), wa_lang=mc.norm(tpl.get("lang")) or "en",
                                wa_params=params, wa_key=wa_template, body=body)
            r.add("template", not problems, "; ".join(problems) or f"`{wa_template}` → {tpl.get('name')}")

    # Pattern (approved content only) and language.
    pattern = find_pattern(root, pattern_id) if pattern_id else None
    if step in SEQ_STEPS or pattern_id:
        pm = pattern.meta if pattern and pattern.meta else {}
        problems = []
        if not pm:
            problems.append(f"pattern `{pattern_id or '(none)'}` not found")
        else:
            if mc.norm(pm.get("status")) != "approved":
                problems.append(f"status `{pm.get('status')}`, not approved")
            if step in SEQ_STEPS and mc.norm(pm.get("step")) != step:
                problems.append(f"step `{pm.get('step')}` ≠ `{step}`")
            if market not in [mc.norm(m) for m in mc.as_list(pm.get("markets"))]:
                problems.append(f"markets {pm.get('markets')} lack {market}")
        r.add("pattern", not problems, "; ".join(problems) or f"`{pattern_id}` approved for {market}/{step}")
        plang = mc.norm(pm.get("lang")) or "en"
        r.add("language", plang == lang,
              f"contact lang `{lang}`, pattern lang `{plang}`" +
              ("" if plang == lang else " — need an approved pattern in that language, or ask the rep"))
    info["pattern"] = pattern_id

    # Products (rule 4).
    catalog = load_products(root)
    unknown = [p for p in products if p not in catalog]
    unavailable = [p for p in products if p in catalog and market not in
                   [mc.norm(m) for m in mc.as_list(catalog[p].get("available_in"))]]
    r.add("products", not unknown and not unavailable,
          "; ".join(filter(None, [f"not in knowledge/products: {unknown}" if unknown else "",
                                  f"not available in {market}: {unavailable}" if unavailable else ""]))
          or f"{products or 'none'} in catalog")

    # Message rules.
    content = strip_boilerplate(body, user)
    words = len(WORD_RE.findall(content))
    if channel == "linkedin":
        r.add("length", len(body) <= LINKEDIN_MAX, f"{len(body)} chars (max {LINKEDIN_MAX})")
    else:
        r.add("length", words <= MAX_WORDS, f"{words} words (max {MAX_WORDS})")
    if channel == "email":
        unsub = [ln for ln in body.splitlines() if UNSUB_RE.search(ln)]
        r.add("unsubscribe", len(unsub) >= 1, unsub[0].strip() if unsub else "no unsubscribe line")
        sig = [ln.strip() for ln in mc.norm(user.get("signature")).splitlines() if ln.strip()]
        r.add("signature", all(s in body for s in sig), "rep signature present" if sig else "rep has no signature")
        today = mc.today().isoformat()
        same_today = [t for t in mc.load_touches(root) if t.get("rep") == me and t.get("status") == "drafted"
                      and t.get("ts", "").startswith(today) and t.get("pattern") == pattern_id and pattern_id]
        bulk = len(same_today) + 1 >= ADV_BULK
        has_adv = subject.strip().upper().startswith("<ADV>")
        if market == "SG":
            r.add("adv", has_adv or not bulk,
                  f"{len(same_today) + 1} drafts today with this pattern" + ("; needs <ADV>" if bulk and not has_adv else ""))
        if step == "first":
            links = URL_RE.findall(body)
            r.add("links", not links, f"no links on a first touch: {links}" if links else "no links")
        ctas = len(re.findall(r"\?", content))
        r.add("cta", 1 <= ctas <= 2, f"{ctas} question(s); one call to action expected")

    # Entity check (rule 5).
    corpus = source_corpus(root, account, [contact], user)
    bad = entity_problems(subject + "\n" + content, corpus)
    r.add("entities", not bad, "; ".join(bad) if bad else "every name, number and date is on the page or in knowledge/")

    win = next_window(mcfg, user.get("send_window_override"))
    info["send_window"] = win
    if channel in ("email", "linkedin", "whatsapp"):
        r.add("send_window", bool(win), win.get("label", "no send day in the next 60 days"))
    info.setdefault("body", body)
    return r, info


def save_draft(root: Path, *, account_id: str, contact_id: str, step: str, channel: str, pattern_id: str,
               products: list[str], subject: str, body: str, user: dict, info: dict) -> Path:
    on = mc.today().isoformat()
    folder = root / "log" / "drafts"
    path = folder / f"{on}-{account_id}-{step}.md"
    n = 2
    while path.exists():
        path = folder / f"{on}-{account_id}-{step}-{n}.md"
        n += 1
    meta = {"type": "draft", "account": account_id, "contact": contact_id, "rep": user.get("id"),
            "market": info.get("market"), "lang": info.get("lang"), "channel": channel, "step": step,
            "pattern": pattern_id, "products": products, "to": info.get("email"), "subject": subject,
            "send_window": (info.get("send_window") or {}).get("date", ""), "ref": "", "created": mc.now_stamp()}
    if channel == "whatsapp":
        meta.update(to=info.get("wa_number", ""), subject="", ref="whatsapp",
                    wa_template=info.get("wa_template", ""), wa_key=info.get("wa_key", ""),
                    wa_lang=info.get("wa_lang", ""), wa_params=info.get("wa_params", []))
        body = info.get("body", body)
    mc.write_page(path, meta, body.rstrip("\n") + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check a draft against AGENTS.md rules and the playbook before it "
                                             "goes to the mailbox; optionally save it to log/drafts/.")
    ap.add_argument("--account", help="account id")
    ap.add_argument("--contact", help="contact id")
    ap.add_argument("--step", choices=STEPS)
    ap.add_argument("--channel", choices=CHANNELS, default="email")
    ap.add_argument("--pattern", default="", help="approved pattern id (required for connect/first/fu*)")
    ap.add_argument("--products", default="", help="product ids, comma- or ;-separated")
    ap.add_argument("--subject", default="")
    ap.add_argument("--file", help="file with the draft body ('-' for stdin); not needed for a WhatsApp template")
    ap.add_argument("--wa-template", default="", help="key in knowledge/whatsapp_templates.yaml (WhatsApp first contact)")
    ap.add_argument("--wa-params", default="", help="template parameters, '|'-separated, in {{1}}, {{2}} order")
    ap.add_argument("--save", action="store_true", help="when every check passes, save to log/drafts/")
    ap.add_argument("--set-ref", nargs=2, metavar=("DRAFT_FILE", "REF"),
                    help="record the mailbox draft id on a saved log/drafts file")
    ap.add_argument("--next-window", action="store_true", help="print the next send window and exit")
    ap.add_argument("--market", help="market for --next-window (default: the account's)")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    user = mc.current_user(root)

    if args.set_ref:
        p = Path(args.set_ref[0])
        p = p if p.is_absolute() else root / p
        if not p.is_file():
            print(f"no such draft file: {args.set_ref[0]}")
            return 1
        mc.update_frontmatter(p, {"ref": args.set_ref[1]})
        print(json.dumps({"ok": True, "file": mc.rel_posix(p, root), "ref": args.set_ref[1]}))
        return 0

    if args.next_window:
        market = args.market
        if not market and args.account:
            page = mc.read_page(root / "wiki" / "accounts" / f"{args.account}.md", root)
            market = mc.norm((page.meta or {}).get("market")) if page else ""
        win = next_window(load_market(root, market or "SG"), (user or {}).get("send_window_override"))
        print(json.dumps(win, ensure_ascii=False))
        return 0 if win else 1

    if not (args.account and args.contact and args.step and (args.file or args.wa_template)):
        ap.error("--account, --contact, --step and --file (or --wa-template) are required")
    body = "" if not args.file else sys.stdin.read() if args.file == "-" else mc.read_text(Path(args.file))
    products = [p.strip() for p in re.split(r"[;,]", args.products) if p.strip()]
    wa_params = [p.strip() for p in args.wa_params.split("|")] if args.wa_params else []
    res, info = run_checks(root, account_id=args.account, contact_id=args.contact, step=args.step,
                           channel=args.channel, pattern_id=args.pattern, products=products,
                           subject=args.subject, body=body, user=user, wa_template=args.wa_template,
                           wa_params=wa_params)
    body = info.get("body", body)
    out = {"ok": res.ok, "checks": res.checks, "send_window": (info.get("send_window") or {}).get("label", ""),
           "to": info.get("wa_number", "") if args.channel == "whatsapp" else info.get("email", "")}
    if args.channel == "whatsapp":
        out["body"] = body
    if args.save and res.ok:
        path = save_draft(root, account_id=args.account, contact_id=args.contact, step=args.step,
                          channel=args.channel, pattern_id=args.pattern, products=products,
                          subject=args.subject, body=body, user=user, info=info)
        out["saved"] = mc.rel_posix(path, root)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
