# ROPA — Verzeichnis von Verarbeitungstätigkeiten (Art. 30 DSGVO)

**Status: pilot-readiness artefact (M6.9).** DACH-DELTA-LAYER §5 requires a ROPA
alongside the sub-processor agreements. This is the **processing-activity view**;
the per-column disposition of every personal-data field is the machine-readable
policy in `app/retention.py`, served at
`GET /api/settings/privacy/retention-policy`.

> **Scope and honesty.** The technical facts below (what is stored, where, who
> can reach it) are derived from the schema and the code and are kept true by the
> tests. Two fields are **legal determinations that engineering did not make and
> must not invent** (CLAUDE.md §6.4) — they are marked `OPEN` and tracked in
> `docs/decisions/DECISIONS.md`:
>
> * the **lawful basis** for vendor-contact personal data, and
> * the **retention window** after which inactive contact PII is purged.
>
> The product therefore implements **on-request** erasure (a settled right that
> needs neither) and **no automatic time-based purge job**.

**Controller:** the operating shop (each tenant is its own controller for its
customer and vendor data). Tolera is the **processor**. Controller identity per
tenant comes from the org's Impressum fields (`app/impressum.py`).

---

## A1 — Quote & order processing (the core activity)

| | |
|---|---|
| **Purpose** | Receiving RFQs, producing quotes, converting to orders |
| **Data subjects** | Employees of customer companies (buyers, engineers) |
| **Categories** | Name, business email, phone, job role, enquiry correspondence, internal notes about the contact |
| **Legal basis** | Art. 6(1)(b) — pre-contractual measures and contract performance |
| **Recipients** | Mailgun EU (correspondence transport); Anthropic (print/email text, non-flagged records only) |
| **Retention** | Order/quote records: **~10 years**, GoBD/HGB immutable (DACH-DELTA §63). Contact identifiers: erased on request; **no automatic window — `OPEN`** |
| **Where** | `contact`, `account`, `request_for_quote`, `quote`, `order_`, `email_message` |
| **Erasure behaviour** | Identifiers anonymised; the commercial record and the enquiry letter itself are retained (see `app/retention.py`) |

## A2 — Vendor sourcing (Vendor RFQ)

| | |
|---|---|
| **Purpose** | Requesting outside-process quotes from suppliers |
| **Data subjects** | Employees of vendor companies (quoting contacts) |
| **Categories** | Name, business email, phone; portal access records |
| **Legal basis** | **`OPEN`** — Art. 6(1)(b) or 6(1)(f) not determined (DECISIONS.md, M6.3 2026-07-19). B2B contact data, stored EU-side, no consent flow (settled by the spec + DACH delta) |
| **Recipients** | Mailgun EU |
| **Retention** | Erased on request; **window `OPEN`** |
| **Where** | `vendor_contact`, `vendor_rfq_recipient`, `quote_token` |
| **Transparency** | The outbound vendor RFQ email carries the org's Impressum footer; the privacy-notice link slots into that same footer once the `OPEN` resolves |

## A3 — Internal user accounts

| | |
|---|---|
| **Purpose** | Authentication, authorisation, attribution of actions |
| **Data subjects** | The shop's own employees |
| **Categories** | Name, work email, role assignments, activity trail (`recent_view`, event tables) |
| **Legal basis** | Art. 6(1)(b) — employment/contract |
| **Recipients** | Clerk (EU residency) |
| **Retention** | For the duration of employment + the audit trails' own retention |
| **Note** | `app_user` is a **platform-wide identity across organisations** (E4-a). Erasing it is a platform-level action, deliberately not exposed on an org admin surface — one tenant must not be able to reach into another |

## A4 — Export-control compliance logging

| | |
|---|---|
| **Purpose** | Evidencing access to, and AI refusal of, EU dual-use flagged records (Reg (EU) 2021/821, AWG/AWV) |
| **Data subjects** | Internal users; external portal visitors |
| **Categories** | Actor id, IP address, user-agent, subject record id, action |
| **Legal basis** | Art. 6(1)(c) — legal obligation (export-control record-keeping) |
| **Retention** | Append-only; **never erased** — erasing it would defeat the obligation it exists to satisfy |
| **Where** | `export_control_access`, `quote_token_access` |
| **Access** | Admin only (`compliance_manage`); CSV export from Settings |

## A5 — AI-assisted extraction and analysis

| | |
|---|---|
| **Purpose** | Lens print/email extraction, RFQ triage brief, requote diff |
| **Data subjects** | Customer contacts (as authors of correspondence) |
| **Categories** | Email bodies, print text |
| **Legal basis** | Art. 6(1)(b), as a means of performing A1 |
| **Recipients** | Anthropic, under DPA, EU-routed, zero-retention requested |
| **Exclusions (enforced in code)** | Export-controlled records are never sent, and every refusal is logged (A4). The per-org AI master flag disables the activity entirely |
| **Human gate** | Output is a **suggestion**: never auto-applied, never fed into pricing (CLAUDE.md §5) |

---

## Technical & organisational measures (Art. 32)

* **Tenant isolation** — PostgreSQL row-level security on every org-scoped table,
  FORCE'd, keyed on a transaction-local GUC. The application connects as a
  restricted role that cannot bypass it.
* **Least privilege** — audit and correspondence tables grant the app role
  `SELECT, INSERT` only; no table grants `DELETE` where a record must survive.
* **Encryption** — OAuth tokens encrypted at rest (`app/email_crypto.py`);
  TLS in transit throughout.
* **Malware scanning** — uploads scanned before they can be downloaded or
  forwarded, self-hosted so no processor is added.
* **Logging discipline** — structured logs carry request-id, org and user, and
  never secrets, customer PII or print contents (CLAUDE.md §5). The compliance
  log enforces this structurally (`app.export_control._check_detail`).
* **Data-subject rights** — `POST /api/settings/privacy/subject-export` and
  `.../subject-erasure`, admin-only, org-scoped by RLS.

## Open items

Both are legal determinations, logged in `DECISIONS.md` and **not** invented here:

1. **Lawful basis for vendor-contact PII** (M6.3, 2026-07-19).
2. **Retention window for inactive contact PII**, reconciled with the GoBD
   retention of the commercial records that reference it.

Until they resolve, the product erases on request and purges nothing on a timer.
