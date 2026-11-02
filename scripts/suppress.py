"""Suppress an email or a whole domain at once (AGENTS.md rule 2, guardrails opt-outs).

Appends `value,type,reason,added_by,added_on` to wiki/suppression.csv (once:
re-running is a no-op), sets every matching contact to `status: do_not_contact`,
and sets the account to `stage: do_not_contact` when it has no active contact
left. Anyone may suppress any contact: an opt-out is never blocked by ownership.

    python3 scripts/suppress.py --email jane@acme.example --reason unsubscribe
    python3 scripts/suppress.py --domain acme.example --reason unsubscribe   # whole company, only on request
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402

FIELDS = ("value", "type", "reason", "added_by", "added_on")
REASONS = ("unsubscribe", "complaint", "bounce", "manager", "legal")


def suppress(root: Path, value: str, kind: str, reason: str, by: str) -> dict:
    value = value.strip().lower().lstrip("@") if kind == "domain" else value.strip().lower()
    path = root / "wiki" / "suppression.csv"
    rows = mc.read_csv(path)
    exists = any(mc.norm(r.get("value")).lower() == value and (mc.norm(r.get("type")) or kind) == kind for r in rows)
    on = mc.today().isoformat()
    if not exists:
        mc.append_csv(path, {"value": value, "type": kind, "reason": reason, "added_by": by, "added_on": on}, FIELDS)

    def matches(email: str) -> bool:
        email = email.lower()
        return email == value if kind == "email" else email.endswith("@" + value) or email.endswith("." + value)

    contacts, accounts = [], set()
    for page in mc.iter_pages("contact", root):
        email = mc.norm(page.meta.get("email"))
        if email and matches(email):
            if mc.norm(page.meta.get("status")) != "do_not_contact":
                mc.update_frontmatter(page.path, {"status": "do_not_contact", "updated": on})
            contacts.append(page.id)
            accounts.add(mc.link_id(page.meta.get("account")))
    if kind == "domain":
        for page in mc.iter_pages("account", root):
            if mc.norm(page.meta.get("domain")).lower() == value:
                accounts.add(page.id)

    stopped = []
    for acc in sorted(a for a in accounts if a):
        p = root / "wiki" / "accounts" / f"{acc}.md"
        page = mc.read_page(p, root) if p.is_file() else None
        if not page or not page.meta:
            continue
        active = [c for c in mc.iter_pages("contact", root)
                  if mc.link_id(c.meta.get("account")) == acc and (mc.norm(c.meta.get("status")) or "active") == "active"
                  and mc.norm(c.meta.get("email"))]
        if (kind == "domain" or not active) and mc.norm(page.meta.get("stage")) != "do_not_contact":
            mc.update_frontmatter(p, {"stage": "do_not_contact", "updated": on})
            stopped.append(acc)
    if not exists:
        mc.append_log("reply", by, "wiki/suppression.csv",
                      f"suppressed {kind} {value} ({reason}); contacts {len(contacts)}, accounts stopped {len(stopped)}",
                      root)
    return {"value": value, "type": kind, "added": not exists, "contacts": contacts, "accounts_stopped": stopped}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Add an email or domain to wiki/suppression.csv and stop its contacts.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--email")
    g.add_argument("--domain")
    ap.add_argument("--reason", default="unsubscribe", choices=REASONS)
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if mc.yaml is None:
        print(mc.YAML_MISSING)
        return 1
    root = mc.repo_root()
    user = mc.current_user(root)
    by = mc.norm((user or {}).get("id")) or "unknown"
    if args.email and "@" not in args.email:
        print("--email needs a full address; use --domain for a whole company")
        return 1
    res = suppress(root, args.email or args.domain, "email" if args.email else "domain", args.reason, by)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
