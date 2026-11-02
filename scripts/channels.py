"""Gmail and WhatsApp Business Cloud API clients for send.py and connect.py (ADR-0007).

Standard library only (urllib, http.server, email). Secrets live OUTSIDE the
repo, in the user's config folder, readable only by them:

    ~/.config/sales-mama/google-oauth-client.json   the team's OAuth client (from the manager)
    ~/.config/sales-mama/gmail.json                 this rep's refresh token + mailbox address
    ~/.config/sales-mama/whatsapp.json              phone-number id, WABA id, access token

Override the folder with env MAMA_CONFIG_DIR. With env MAMA_SEND_TRANSPORT=fake
nothing leaves the machine: Gmail drafts are read from the saved log/drafts file
and every send returns a fake id (used by selftest.py).

Import only; for setup run `python3 scripts/connect.py`.
"""
from __future__ import annotations

import base64
import email
import email.policy
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
GMAIL_SCOPES = ("https://www.googleapis.com/auth/gmail.compose",
                "https://www.googleapis.com/auth/gmail.readonly")
GRAPH = "https://graph.facebook.com/v21.0"
E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
TIMEOUT = 30


class ChannelError(Exception):
    """A channel call failed; the message is safe to show (no secrets)."""


# ----------------------------------------------------------------------------
# Config folder (secrets never go in the repo)
# ----------------------------------------------------------------------------
def config_dir() -> Path:
    env = os.environ.get("MAMA_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "sales-mama"


def fake() -> bool:
    return os.environ.get("MAMA_SEND_TRANSPORT", "").strip().lower() == "fake"


def read_secret(name: str) -> dict:
    p = config_dir() / name
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_secret(name: str, data: dict) -> Path:
    folder = config_dir()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(folder, 0o700)
    except OSError:
        pass
    p = folder / name
    tmp = p.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, p)
    return p


def body_hash(*parts: str) -> str:
    norm = "\n".join(re.sub(r"\s+", " ", (p or "")).strip() for p in parts)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------
def _http(method: str, url: str, *, token: str = "", data: dict | None = None, form: dict | None = None) -> dict:
    headers = {"Accept": "application/json"}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
            err = detail.get("error")
            msg = err.get("message") if isinstance(err, dict) else (detail.get("error_description") or err)
        except Exception:  # noqa: BLE001
            msg = exc.reason
        raise ChannelError(f"HTTP {exc.code}: {msg}") from None
    except urllib.error.URLError as exc:
        raise ChannelError(f"network error: {exc.reason}") from None


# ----------------------------------------------------------------------------
# Gmail
# ----------------------------------------------------------------------------
def google_client() -> dict:
    """client_id / client_secret from the OAuth client file the manager handed out."""
    data = read_secret("google-oauth-client.json")
    inner = data.get("installed") or data.get("web") or data
    return {"client_id": inner.get("client_id", ""), "client_secret": inner.get("client_secret", "")}


def gmail_status() -> dict:
    if fake():
        return {"ok": True, "email": os.environ.get("MAMA_USER_EMAIL", ""), "detail": "fake transport"}
    tok = read_secret("gmail.json")
    if not google_client()["client_id"]:
        return {"ok": False, "email": "", "detail": f"no OAuth client: put the file from your manager at "
                                                    f"{config_dir() / 'google-oauth-client.json'}"}
    if not tok.get("refresh_token"):
        return {"ok": False, "email": "", "detail": "not connected: run `python3 scripts/connect.py gmail`"}
    return {"ok": True, "email": tok.get("email", ""), "detail": "connected"}


def gmail_access_token() -> str:
    tok, client = read_secret("gmail.json"), google_client()
    if not tok.get("refresh_token") or not client["client_id"]:
        raise ChannelError("Gmail is not connected: run `python3 scripts/connect.py gmail`")
    res = _http("POST", GOOGLE_TOKEN, form={"client_id": client["client_id"], "client_secret": client["client_secret"],
                                             "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"})
    if not res.get("access_token"):
        raise ChannelError("Gmail sign-in expired: run `python3 scripts/connect.py gmail` again")
    return res["access_token"]


def gmail_profile(token: str) -> dict:
    return _http("GET", f"{GMAIL}/profile", token=token)


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _plain_body(msg: email.message.Message) -> str:
    part = msg.get_body(preferencelist=("plain",)) if hasattr(msg, "get_body") else None
    if part is None:
        for p in msg.walk():
            if p.get_content_type() == "text/plain":
                part = p
                break
    if part is None:
        return ""
    try:
        return part.get_content()
    except Exception:  # noqa: BLE001
        payload = part.get_payload(decode=True) or b""
        return payload.decode(part.get_content_charset() or "utf-8", "replace")


def _fake_draft(root: Path, ref: str, draft_file: Path | None) -> dict:
    path = draft_file
    if path is None:
        for p in sorted((root / "log" / "drafts").glob("*.md")):
            page = mc.read_page(p, root)
            if page and page.meta and mc.norm(page.meta.get("ref")) == ref:
                path = p
                break
    page = mc.read_page(path, root) if path and path.is_file() else None
    if not page or not page.meta:
        raise ChannelError(f"draft {ref} not found")
    m = page.meta
    return {"id": ref or f"fake-draft-{path.stem}", "to": mc.norm(m.get("to")), "subject": mc.norm(m.get("subject")),
            "body": page.body, "cc": "", "bcc": "", "raw": None}


def gmail_get_draft(root: Path, ref: str, draft_file: Path | None = None, token: str = "") -> dict:
    """{id, to, subject, body, cc, bcc, raw} of a Gmail draft, read live (the rep may have edited it)."""
    if fake():
        return _fake_draft(root, ref, draft_file)
    res = _http("GET", f"{GMAIL}/drafts/{urllib.parse.quote(ref)}?format=raw", token=token)
    raw = (res.get("message") or {}).get("raw", "")
    msg = email.message_from_bytes(_b64d(raw), policy=email.policy.default)
    return {"id": res.get("id", ref), "to": str(msg.get("To", "")), "subject": str(msg.get("Subject", "")),
            "body": _plain_body(msg), "cc": str(msg.get("Cc", "") or ""), "bcc": str(msg.get("Bcc", "") or ""),
            "raw": raw}


def gmail_create_draft(root: Path, *, sender: str, to: str, subject: str, body: str, token: str = "",
                       draft_file: Path | None = None) -> str:
    if fake():
        return f"fake-draft-{draft_file.stem if draft_file else 'x'}"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    res = _http("POST", f"{GMAIL}/drafts", token=token, data={"message": {"raw": raw}})
    return res.get("id", "")


def gmail_send_draft(draft: dict, *, unsubscribe_to: str, token: str = "") -> str:
    """Add a List-Unsubscribe header, then send that exact draft. Returns the Gmail message id."""
    if fake():
        return "fake-" + hashlib.sha1((draft.get("id") or "").encode()).hexdigest()[:12]
    if draft.get("raw") and unsubscribe_to:
        msg = email.message_from_bytes(_b64d(draft["raw"]), policy=email.policy.default)
        if "List-Unsubscribe" not in msg:
            msg["List-Unsubscribe"] = f"<mailto:{unsubscribe_to}?subject=unsubscribe>"
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            _http("PUT", f"{GMAIL}/drafts/{urllib.parse.quote(draft['id'])}", token=token,
                  data={"id": draft["id"], "message": {"raw": raw}})
    res = _http("POST", f"{GMAIL}/drafts/send", token=token, data={"id": draft["id"]})
    if not res.get("id"):
        raise ChannelError("Gmail returned no message id")
    return res["id"]


# ----------------------------------------------------------------------------
# WhatsApp Business Cloud API
# ----------------------------------------------------------------------------
def whatsapp_status() -> dict:
    if fake():
        return {"ok": True, "number": "+6500000000", "detail": "fake transport"}
    cfg = read_secret("whatsapp.json")
    if not (cfg.get("phone_number_id") and cfg.get("token")):
        return {"ok": False, "number": "", "detail": "not connected: run `! python3 scripts/connect.py whatsapp`"}
    return {"ok": True, "number": cfg.get("display_number", ""), "detail": "connected"}


def whatsapp_check(phone_number_id: str, token: str) -> dict:
    return _http("GET", f"{GRAPH}/{urllib.parse.quote(phone_number_id)}?fields=display_phone_number,verified_name",
                 token=token)


def whatsapp_templates(waba_id: str, token: str) -> list[dict]:
    res = _http("GET", f"{GRAPH}/{urllib.parse.quote(waba_id)}/message_templates?fields=name,language,status&limit=200",
                token=token)
    return list(res.get("data") or [])


def whatsapp_send(*, to: str, template: str = "", lang: str = "en", params: list[str] | None = None,
                  text: str = "") -> str:
    """Send a template (first contact) or free text (within 24 h of the contact's reply). Returns the wamid."""
    if not E164_RE.match(to or ""):
        raise ChannelError(f"WhatsApp number {to!r} is not in +E.164 form")
    if fake():
        return "wamid.fake-" + hashlib.sha1(f"{to}{template}{text}".encode()).hexdigest()[:12]
    cfg = read_secret("whatsapp.json")
    if not (cfg.get("phone_number_id") and cfg.get("token")):
        raise ChannelError("WhatsApp is not connected: run `! python3 scripts/connect.py whatsapp`")
    payload: dict = {"messaging_product": "whatsapp", "to": to.lstrip("+")}
    if template:
        comp = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in (params or [])]}]
        payload.update(type="template", template={"name": template, "language": {"code": lang},
                                                  **({"components": comp} if params else {})})
    else:
        payload.update(type="text", text={"preview_url": False, "body": text})
    res = _http("POST", f"{GRAPH}/{urllib.parse.quote(cfg['phone_number_id'])}/messages", token=cfg["token"],
                data=payload)
    msgs = res.get("messages") or []
    if not msgs or not msgs[0].get("id"):
        raise ChannelError("WhatsApp returned no message id")
    return msgs[0]["id"]


if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description="Gmail and WhatsApp clients for send.py and connect.py (import only). "
                                        "Set up channels with `python3 scripts/connect.py`.").parse_args()
