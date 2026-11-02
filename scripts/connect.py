"""Connect a rep's sending channels in one command each (ADR-0007).

    python3 scripts/connect.py gmail [--client-file ~/Downloads/client_secret_….json]
    ! python3 scripts/connect.py whatsapp      # type the token yourself; it never reaches the chat
    python3 scripts/connect.py status [--json]

gmail     Opens Google sign-in in the browser (loopback + PKCE); you click Allow.
          Scopes: gmail.compose (create and send drafts) and gmail.readonly (Sent and
          reply checks). The refresh token is saved to ~/.config/sales-mama/gmail.json
          (mode 600), never in the repo. --client-file copies the team's OAuth client
          (from the manager) into place first.
whatsapp  Asks for the phone-number ID, the WhatsApp Business Account ID and a System
          User token, checks them against the Cloud API, compares approved templates
          with knowledge/whatsapp_templates.yaml and saves to ~/.config/sales-mama/whatsapp.json.
status    Sending switch, Gmail and WhatsApp state and template coverage. No secrets printed.

Connecting does not send anything. Sending needs knowledge/sending.yaml `enabled: true`
(manager) and the rep's approval of each batch in /mama-send.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import channels as ch  # noqa: E402
import mama_common as mc  # noqa: E402

LOGIN_TIMEOUT = 300


def sending_cfg(root: Path) -> dict:
    data = mc.load_yaml(root / "knowledge" / "sending.yaml", {}) or {}
    return data if isinstance(data, dict) else {}


def wa_templates_cfg(root: Path) -> dict:
    data = mc.load_yaml(root / "knowledge" / "whatsapp_templates.yaml", {}) or {}
    tpl = data.get("templates") if isinstance(data, dict) else None
    return tpl if isinstance(tpl, dict) else {}


# ----------------------------------------------------------------------------
# Gmail
# ----------------------------------------------------------------------------
def _install_client(path: str) -> None:
    src = Path(path).expanduser()
    data = json.loads(src.read_text(encoding="utf-8"))
    inner = data.get("installed") or data.get("web") or {}
    if not inner.get("client_id"):
        raise SystemExit(f"{src} is not a Google OAuth client file (no client_id)")
    ch.write_secret("google-oauth-client.json", data)
    print(f"OAuth client installed in {ch.config_dir()}")


def connect_gmail(root: Path, client_file: str | None, no_browser: bool) -> int:
    if client_file:
        _install_client(client_file)
    client = ch.google_client()
    if not client["client_id"]:
        print(f"No OAuth client yet. Ask your manager for the Sales Mama Google client file, then run:\n"
              f"  python3 scripts/connect.py gmail --client-file <path to the .json>")
        return 1
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)
    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] != state:
                self.send_response(400)
                self.end_headers()
                return
            result["code"] = q.get("code", [""])[0]
            result["error"] = q.get("error", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Sales Mama is connected to Gmail. You can close this tab." if result["code"] else \
                "Sign-in was cancelled. You can close this tab."
            self.wfile.write(f"<p style='font:16px system-ui;margin:3em'>{msg}</p>".encode())

        def log_message(self, *a):  # silence
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{server.server_port}"
    url = ch.GOOGLE_AUTH + "?" + urllib.parse.urlencode({
        "client_id": client["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(ch.GMAIL_SCOPES), "access_type": "offline", "prompt": "consent",
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state})
    print("Opening Google sign-in. Choose your work mailbox and click Allow.")
    print(f"If the browser doesn't open, visit:\n  {url}")
    if not no_browser:
        webbrowser.open(url)
    server.timeout = LOGIN_TIMEOUT
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()
    t.join(LOGIN_TIMEOUT + 5)
    server.server_close()
    if not result.get("code"):
        print(f"Gmail not connected: {result.get('error') or 'no answer from the browser within 5 minutes'}")
        return 1
    try:
        tok = ch._http("POST", ch.GOOGLE_TOKEN, form={
            "client_id": client["client_id"], "client_secret": client["client_secret"], "code": result["code"],
            "code_verifier": verifier, "grant_type": "authorization_code", "redirect_uri": redirect})
        if not tok.get("refresh_token"):
            print("Google returned no refresh token. Remove Sales Mama at myaccount.google.com/permissions and retry.")
            return 1
        profile = ch.gmail_profile(tok["access_token"])
    except ch.ChannelError as exc:
        print(f"Gmail not connected: {exc}")
        return 1
    mailbox = profile.get("emailAddress", "")
    ch.write_secret("gmail.json", {"refresh_token": tok["refresh_token"], "email": mailbox,
                                   "scopes": list(ch.GMAIL_SCOPES), "connected": mc.now_stamp()})
    user = mc.current_user(root)
    print(f"Gmail connected: {mailbox}")
    if user and mailbox.lower() != mc.norm(user.get("email")).lower():
        print(f"Note: your profile email is {user.get('email')}. send.py only sends from the mailbox that "
              f"matches reps/{user['id']}.md, so connect that mailbox or ask the manager to update your profile.")
    return 0


# ----------------------------------------------------------------------------
# WhatsApp
# ----------------------------------------------------------------------------
def connect_whatsapp(root: Path, phone_id: str | None, waba_id: str | None) -> int:
    phone_id = phone_id or input("Phone-number ID (WhatsApp Manager → API setup): ").strip()
    waba_id = waba_id or input("WhatsApp Business Account ID: ").strip()
    token = os.environ.get("WHATSAPP_TOKEN") or getpass.getpass("System User access token (hidden): ").strip()
    if not (phone_id and waba_id and token):
        print("WhatsApp not connected: phone-number ID, account ID and token are all needed.")
        return 1
    try:
        info = ch.whatsapp_check(phone_id, token)
        approved = {t.get("name") for t in ch.whatsapp_templates(waba_id, token)
                    if str(t.get("status", "")).upper() == "APPROVED"}
    except ch.ChannelError as exc:
        print(f"WhatsApp not connected: {exc}")
        return 1
    ch.write_secret("whatsapp.json", {"phone_number_id": phone_id, "waba_id": waba_id, "token": token,
                                      "display_number": info.get("display_phone_number", ""),
                                      "verified_name": info.get("verified_name", ""), "connected": mc.now_stamp()})
    print(f"WhatsApp connected: {info.get('verified_name', '')} {info.get('display_phone_number', '')}")
    mapped = wa_templates_cfg(root)
    missing = sorted(k for k, v in mapped.items() if (v or {}).get("name") not in approved)
    print(f"Templates: {len(approved)} approved in Meta; {len(mapped) - len(missing)} of {len(mapped)} "
          f"mapped in knowledge/whatsapp_templates.yaml are usable.")
    for k in missing:
        print(f"  - {k}: template `{(mapped[k] or {}).get('name')}` is not approved in WhatsApp Manager yet")
    return 0


# ----------------------------------------------------------------------------
# Status
# ----------------------------------------------------------------------------
def status(root: Path) -> dict:
    cfg = sending_cfg(root)
    user = mc.current_user(root)
    gm, wa = ch.gmail_status(), ch.whatsapp_status()
    if gm["ok"] and user and gm["email"] and gm["email"].lower() != mc.norm(user.get("email")).lower():
        gm = {**gm, "ok": False, "detail": f"connected to {gm['email']}, but your profile is {user.get('email')}"}
    return {"sending_enabled": bool(cfg.get("enabled")),
            "channels": {"email": bool((cfg.get("channels") or {}).get("email", True)),
                         "whatsapp": bool((cfg.get("channels") or {}).get("whatsapp", True))},
            "gmail": gm, "whatsapp": wa, "whatsapp_templates": len(wa_templates_cfg(root)),
            "user": (user or {}).get("id")}


def status_line(root: Path) -> str:
    s = status(root)
    parts = ["Sending: " + ("on" if s["sending_enabled"] else "off (knowledge/sending.yaml)"),
             "Gmail " + ("ok" if s["gmail"]["ok"] else "not connected"),
             "WhatsApp " + ("ok" if s["whatsapp"]["ok"] else "not connected")]
    return " · ".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Connect Gmail and WhatsApp for approve-then-send (ADR-0007). "
                                             "Secrets are stored outside the repo.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gmail", help="sign in to your work mailbox (opens the browser)")
    g.add_argument("--client-file", help="the team's Google OAuth client .json from the manager")
    g.add_argument("--no-browser", action="store_true", help="print the sign-in link instead of opening it")
    wsp = sub.add_parser("whatsapp", help="connect the WhatsApp Business Cloud API (run with `!` so you type the token)")
    wsp.add_argument("--phone-number-id")
    wsp.add_argument("--waba-id")
    st = sub.add_parser("status", help="show what is connected (no secrets)")
    st.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    if os.environ.get("MAMA_RUNNER") and args.cmd != "status":
        print("connect.py is for people, not the nightly runner.")
        return 1
    if args.cmd == "gmail":
        return connect_gmail(root, args.client_file, args.no_browser)
    if args.cmd == "whatsapp":
        return connect_whatsapp(root, args.phone_number_id, args.waba_id)
    s = status(root)
    if args.json:
        print(json.dumps(s, indent=2))
    else:
        print(status_line(root))
        print(f"  Gmail:    {s['gmail']['detail']}" + (f" ({s['gmail']['email']})" if s['gmail'].get('email') else ""))
        print(f"  WhatsApp: {s['whatsapp']['detail']}" + (f" ({s['whatsapp']['number']})" if s['whatsapp'].get('number') else ""))
        print(f"  WhatsApp templates mapped: {s['whatsapp_templates']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
