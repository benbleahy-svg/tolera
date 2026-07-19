# Sub-processor register (AVV / DPA status)

**Status: pilot-readiness artefact (M6.9).** DACH-DELTA-LAYER §5 requires an
"**AVV/DPA** with every sub-processor (Clerk, Mailgun EU, LLM provider, hosting)"
plus an **EU data-residency** assertion. This file is the register those
agreements attach to; it is the human-maintained companion to the machine-readable
retention policy at `GET /api/settings/privacy/retention-policy`
(`app/retention.py`).

> **This register records engineering facts, not legal advice.** The *technical*
> columns (region, what data reaches the processor, how it is configured) are
> derived from the code and are kept true by it. The **DPA-signed** column is a
> paperwork state only Benjamin can set — it is deliberately left honest rather
> than optimistic, and `⬜` means *not confirmed to me*, not *not signed*.

## Register

| Sub-processor | Purpose | Region / residency | Personal data it receives | Configured in | DPA/AVV signed |
|---|---|---|---|---|---|
| **Hetzner** (Cloud + Object Storage) | Application hosting, PostgreSQL, Redis, CAD/print blob storage | EU (Nürnberg / Falkenstein / Helsinki) — `build-plan/M0.0 §3` | Everything the product stores: contacts, accounts, RFQ correspondence, part files | Deployment/infra | ⬜ |
| **Clerk** | Authentication + organisation identity (internal users only) | EU data residency enabled — `M0.0 §4` | Internal users' email + name. **No customer or vendor data.** | `app/auth.py` | ⬜ |
| **Mailgun** | Inbound RFQ ingest + outbound quote/vendor email | **EU region** (`api.eu.mailgun.net`) — `app/config.py`, `M0.0 §5` | Message envelopes and bodies: customer/vendor addresses, names, enquiry text, attachments | `app/email_providers.py` | ⬜ |
| **Anthropic** (Claude) | Lens extraction, triage brief, requote diff, rule suggestion | EU-routed per the DPA; zero-retention / no-training requested — `M0.0 §6` | Print text and email bodies **for non-flagged records only** — see the exclusion below | `app/lens_provider.py` | ⬜ |
| **Paddle** | Billing (merchant of record) | EU | Billing contact of the *shop*, not its customers | Deferred (`M0.0 §10`) | ⬜ |

### Deliberately *not* sub-processors

* **ClamAV** — upload malware scanning runs **self-hosted in our own
  infrastructure** (`docker-compose.yml`, `app/av.py`) precisely so that
  scanning customer CAD does not add a processor. Files never leave for a scan.
* **Restricted-party screening** — ships with no provider configured
  (`NullScreeningProvider`, `app/services/screening.py`). Wiring a real
  sanctions-list provider **adds a sub-processor** and requires a new row here
  before it goes live.

## What the LLM never receives

Two exclusions are enforced in code, not by policy alone:

1. **Export-controlled (EU dual-use) records.** Every AI entrypoint refuses a
   flagged record before any bytes leave, and records the refusal in the
   export-control compliance log — `lens_extract`, `triage`, `requote_diff`,
   `vendor_reply_lens`, `email_parts`. The evidence is exportable as CSV from
   Settings ("CUI Audit").
2. **Anything, when the org disables AI.** The per-org master flag
   (`app/ai_settings.py`) turns every feature to manual entry.

`app/rule_suggest.py` calls Claude with aggregate counts only — operation name,
process family, material class, part count, window. No part identity, no
geometry, no file bytes, no personal data.

## EU data-residency assertion

Every processor above is configured to an EU region, and the product's own
storage (PostgreSQL + object storage) is EU-hosted. No US-region service is in
the request path.

## Keeping this file true

Adding a sub-processor means: a row here, a DPA before it handles live data, and
a corresponding entry in `ROPA.md`. A new outbound integration
(`app/services/`) that transmits personal data is the trigger to check.
