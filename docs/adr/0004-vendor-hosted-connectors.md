# ADR-0004: Vendor-hosted connectors only in v1

- **Status:** accepted
- **Context:** Self-hosted MCP servers in a previous build needed extra hardening (DNS-rebinding protection, timeouts, retries, deployment work).
- **Decision:** v1 uses vendor-hosted connectors (email; later CRM) with per-user sign-in and the narrowest scopes. No self-hosted MCP server. If one is added later, it binds to localhost, sets timeouts and retries, and gets its own ADR.
- **Consequences:** less to run; connector availability and scopes depend on the vendor and IT approval.
