# ADR-0001: Drafts only — humans send

- **Status:** accepted
- **Context:** In a previous build, design documents disagreed on whether the assistant could send email, which delayed approvals. Sending is irreversible and carries compliance risk in every market.
- **Decision:** Sales Mama never sends email, WhatsApp, SMS or LinkedIn messages. It creates mailbox drafts (email) or text for manual sending (other channels). Email send tools are denied in `.claude/settings.json`; Codex limits `enabled_tools`; Microsoft 365 is granted `Mail.ReadWrite`, never `Mail.Send`.
- **Consequences:** reps keep a final review step; send windows are advisory text; reply tracking marks a touch `sent` only when it appears in the Sent folder.
