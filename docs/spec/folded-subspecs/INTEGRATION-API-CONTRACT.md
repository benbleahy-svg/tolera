# Integration & API Contract — Sub-Spec

**Status:** Build-readiness appendix for Tolera (Bid Factory). Defines the two outward-facing APIs (REST + Streaming/webhooks) and the **Managed Integrations** framework that wraps them, so a third party — or our own DATEV/ERP connectors — can read/write Tolera data and react to events. **Provenance:** `integration-development-guide`, `paperless-parts-streaming-api`, `integration-manager` (+ `autodesk-fusion-integration`, `integration-actions` for context). Companions: `DOMAIN-MODEL.md` (entities the REST surface exposes), `DB-SCHEMA.sql`, `DACH-DELTA-LAYER.md` (which connectors replace the US set), `DECISIONS.md` (managed-connector + MSSQL deferred post-pilot).

> **Phasing (per `DECISIONS.md`).** The **REST API + outbound webhooks** are v1 (DATEV/ERP export, Paddle billing, Mailgun EU ingest all need them). The full **Managed-Integrations UI** (in-app Integration Manager, action logs, in-context action requests, scheduling) is **post-pilot** — but we define the contract now so the data model and event bus are built once, correctly. Mark each section v1 / post-pilot.

---

## 1. The two APIs (mental model)

Paperless exposes **two** complementary APIs; Tolera mirrors the split.

| API | Direction | Initiator | Use it for |
|---|---|---|---|
| **REST API** | client → Tolera | client | Ask questions about data; create/update/delete data. Request/response. |
| **Streaming API (webhooks)** | Tolera → client | Tolera | React to something that *happened* in Tolera, in near-real-time. |

The REST API is wrong for "tell me when X happens" — that forces polling, which is inefficient (most intervals are empty) and hits rate limits. The Streaming API solves that: **Tolera POSTs to the client** when an event occurs. Build both; they share the event catalog (§3).

---

## 2. Managed Integrations framework (the wrapper) — *post-pilot UI, v1 data model*

The framework lets a user **manage, monitor, and trigger** an external integration **from inside Tolera**, so they don't jump between systems and the integration developer doesn't have to build a separate UI. Four record types:

- **Integration Manager** — one per connected external system (e.g. "DATEV", "ProAlpha ERP"). Houses config + logs + connectivity (API token, webhooks). Lives under org **Settings → Integrations**. Requires *Configure* permission on Integrations; **API token visible to Admin only**.
- **Integration Action Definition** — a *description of a capability* (e.g. "Export Quote", "Import Contact", "Bulk Import Contacts"). Fields:
  - `type` (machine key), `display_title`, `display_description`
  - `has_tolera_entity` (bool) + `entity_type` (quote | order | account | contact | …) — if set, the user gets an entity-picker when requesting, can filter logs by it, and the action surfaces *in-context* on that entity's screen.
  - `can_be_requested` (bool) — show a manual "request" button. *UI flag only; the integration itself must be able to receive and act on the request.*
  - `notify_on_failure` (bool) — generate in-app notifications on failure (§6).
- **Integration Action (log)** — a record of one attempt to perform an action, with `status ∈ {queued, in_progress, completed, failed, cancelled, timed_out}`, `status_message`, `last_updated`, optional `related_object` (the quote/order). The audit trail the end-user sees. Populated by the integration via REST.
- **Integration Action Request** — a user-initiated request to run an action. Delivered to the integration as an **event** of type `integration_action.requested`; Tolera auto-creates the matching Integration Action log in `queued` so the user gets immediate feedback (and doesn't double-request).

**Lifecycle the integration should follow:** receive trigger (event) → create/find the Action log → set `in_progress` → do work async → set terminal status + human-readable `status_message`. (For *requested* actions the `queued` log already exists; just update it.) Note: in PP the `status_message` is surfaced to the user only for `completed`/`cancelled` — write messages accordingly.

**Health / heartbeat** — optional `show_status_indicator`; integration POSTs a heartbeat (~every 5 min) so the user can see "last phoned home" and trust the integration is live before requesting an action.

**Pause / Play** — user can disable an integration; delivered as `integration.turned_off` / `integration.turned_on` events. The integration must honor them.

**Scheduling** — only Action Definitions with **no** Tolera entity can be scheduled (a scheduled run has no opportunity for the user to pick an entity). E.g. "Bulk Import Contacts, daily".

**In-context (post-pilot):** in PP, only **Quote**-tied actions are triggerable in-context (Quote → Actions → Relevant Integrations). Tolera: keep the same constraint for v-next; design entity-scoping generically.

---

## 3. Event catalog (the bus)

Events are **facts about things that happened**, generated automatically by Tolera. They drive both webhooks (push) and the Events polling endpoint (pull). Start from PP's set; the catalog grows over time.

**v1 (inherited from PP):**

| Event type | Fires when |
|---|---|
| `quote.created` | a quote is created |
| `quote.status_changed` | quote status transitions (see `qi_workflow_status`/quote status enums in `DB-SCHEMA.sql`) |
| `quote.sent` | quote is sent to the customer |
| `order.created` | an order is created (quote → order) |
| `order.status_changed` | order status transitions |
| `integration_action.requested` | user issues an Integration Action Request (a *special event*; fetch like any other) |
| `integration.turned_on` / `integration.turned_off` | user pauses/plays an integration |

**Tolera additions to plan for (DACH/our net-new — gate behind config):** `rfq.received` (Mailgun ingest), `quote.approved` (internal approval gate), `invoice.issued` / `einvoice.exported` (XRechnung/ZUGFeRD/DATEV), `order.shipped`. Keep names `noun.verb_past`. Each new event is additive; never repurpose an existing name.

**Dispatch semantics:** when an event is first read via the Events list endpoint it is marked **dispatched** (like "read"); clients can filter `dispatched=false` to poll only new events. Webhook delivery is independent of the dispatched flag.

---

## 4. Streaming API — webhooks (v1)

### 4.1 Configure
Integration Manager → **Connectivity → Create Webhook**. Supply an **HTTPS, publicly reachable** endpoint URL + select subscribed event types. Tolera generates a **signing secret** per webhook. A delivery log (sortable/filterable by name, response status code, timestamp) records each dispatch's POST body **and** the client's response.

### 4.2 Delivery
On each subscribed event, Tolera sends an **HTTPS POST**. The endpoint must **respond immediately (2xx) on receipt**; do all business logic **asynchronously** (enqueue + return). Sample body (PP shape — Tolera keeps it):

```json
{
  "created": "2026-06-21T18:49:45.893180Z",
  "data": {
    "type": "bulk_import_contacts",
    "uuid": "6c96b208-2cc9-4356-b6a1-f1ee9a8fb9b2",
    "status": "requested",
    "created": "2026-06-21T18:49:45.890275Z",
    "updated": "2026-06-21T18:49:45.890298Z",
    "entity_id": null,
    "related_object": null,
    "status_message": null,
    "related_object_type": null
  },
  "object": "integration action",
  "type": "integration_action.requested"
}
```

`data` shape varies by event `object` type (integration action vs quote vs order). Define a typed payload per event in the OpenAPI doc; always include `type`, `created`, and a stable entity `uuid`.

### 4.3 Signature verification (required)
Every dispatch carries a **`Tolera-Signature`** header (PP: `Paperless-Parts-Signature`) of the form `t=<unix_ts>,v1=<hex_hmac>`. The timestamp is folded into the signature to prevent replay. To verify:

1. Split header into `timestamp` and `v1` signature.
2. Build `message = f"{timestamp}.{raw_json_body}"`.
3. Compute `HMAC-SHA256(key=unhexlify(signing_secret), msg=message)` → hex.
4. Constant-time compare with `v1`. **Reject on mismatch** (and optionally reject if `timestamp` is too old).

Reference (PP, adapt header name):

```python
import binascii, hashlib, hmac, json

def create_hmac_signature(payload: dict, signing_secret: str, timestamp: int) -> str:
    message = f"{timestamp}.{json.dumps(payload)}".encode()
    key = binascii.unhexlify(signing_secret)
    return hmac.new(key, message, hashlib.sha256).hexdigest()
```

> **Build note:** sign over the **exact raw bytes** we transmit; if the client re-serializes JSON the signature breaks (key ordering/whitespace). Document that the signed body is the verbatim request body, and on our side compute the signature from the same serialized buffer we send.

### 4.4 Reliability (Tolera net-new — PP under-specifies)
Define and document: retry policy (exponential backoff on non-2xx, N attempts), at-least-once delivery (consumers must be **idempotent** on event `uuid`), per-dispatch delivery log retention, and a manual "resend" affordance. Webhook endpoints are **standing configuration** → creating/editing one is a permissioned, audited action (see platform safety rules).

---

## 5. REST API surface (v1)

Backbone for DATEV/ERP export, billing, and our own connectors. Conventions:

- **Base:** `https://api.tolera.eu/v1` (EU data residency — see `DACH-DELTA-LAYER.md`/GDPR).
- **Auth:** per-integration **API token** (bearer), managed on the Integration Manager Connectivity tab, **Admin-only** visibility. Tokens are org-scoped → every call is implicitly tenant-filtered (RLS in `DB-SCHEMA.sql`). Internal app uses Clerk session auth; **machine integrations use tokens, not user credentials.**
- **Format:** JSON; `snake_case`; ISO-8601 UTC timestamps; monetary values as integer minor units **with explicit `currency`** (EUR/CHF — never a bare float; see DACH money rules). Entity ids are UUIDs.
- **Pagination:** cursor or `page`/`page_size`; return `next`/`previous`. Events endpoint additionally filters by `type` and `dispatched`.
- **Rate limiting:** documented per-token limit + `429` + `Retry-After`; this is *the* reason to prefer webhooks over polling.
- **Errors:** consistent envelope `{error: {code, message, details[]}}`; 4xx client / 5xx server; validation errors enumerate offending fields.

**Resource map (derive shapes from `DOMAIN-MODEL.md` / `DB-SCHEMA.sql`):**

| Resource | Verbs (v1) | Notes |
|---|---|---|
| `quotes` | list/get/create/update | + `/quotes/{id}/send`; nested quote_items → components → component_quantities (read) |
| `orders` | list/get/(create) | created from accepted quote |
| `accounts`, `contacts` | list/get/create/update | CRM import target (DATEV/ERP, replaces QuickBooks customer sync) |
| `parts` | list/get | part library; files/geometry read |
| `events` | **list/get** | polling alternative to webhooks; filter `type`, `dispatched` |
| `integration_managers` | get/update | config |
| `integration_actions` | **create/update**, list/get | the log records the integration writes (`POST` to create in `queued`, `PATCH` status) |
| `integration_action_definitions` | list/get | discover capabilities |
| `webhooks` | create/update/delete, list | standing config (permissioned) |
| heartbeat | `POST /integration/heartbeat` | status indicator |

> **Prohibited via API per platform rules:** no endpoint may let an integration alter **sharing/permissions/ACLs**, **hard-delete** data, change **security settings**, or move **funds**. Billing state changes come *from* Paddle webhooks *into* Tolera, not the reverse. Keep these server-enforced regardless of token scope.

---

## 6. Notifications (post-pilot UI; failure semantics v1)

In-app notification generated per user when **all** hold: the Action Definition has `notify_on_failure=true`; the user has *View logs* (or higher) on Integrations; an Action log goes `failed | cancelled | timed_out`. The notification names the action + related object (order/quote). PP default: only **export** actions notify on failure unless configured — keep that default (exports to DATEV/ERP failing silently is the dangerous case).

---

## 7. DACH connector set (replaces the US/QuickBooks set)

Per `DACH-DELTA-LAYER.md`, the integration *targets* differ even though the framework is identical:

- **Accounting/DATEV** (not QuickBooks): export invoices/customers via DATEV format; this is the priority outbound connector. Drives `invoice.issued`/`einvoice.exported` events.
- **E-invoicing**: XRechnung / ZUGFeRD 2.1+ / Peppol export (German B2B e-invoicing timeline: receive 2025 / issue >€800k 2027 / all 2028). Likely an Integration Action ("Export E-Invoice") + a generated artifact, GoBD-archived (see `einvoice` table in `DB-SCHEMA.sql`).
- **German/EU ERPs** (e.g. ProAlpha, abas, SAP B1) in place of generic US ERP — managed-connector pattern, **post-pilot**.
- **Email**: Mailgun **EU** for inbound RFQ ingest (`{org-slug}@rfq.tolera.eu`) + outbound; inbound parsing feeds the Lens engine, not this REST surface, but `rfq.received` rides the same event bus.
- **Billing**: Paddle (EU MoR) webhooks **into** Tolera for subscription state.
- **CAD**: PP ships an Autodesk Fusion plugin (push parts/quotes from CAD). Tolera equivalent is **post-pilot**; the upload + REST `parts`/`quotes` endpoints are the contract it would use.

---

## 8. Acceptance criteria

- **Webhook round-trip:** subscribe to `quote.sent`; sending a quote POSTs a correctly-**signed** payload; a tampered body fails verification and is rejected; endpoint returns 2xx synchronously and processes async.
- **Idempotency:** delivering the same event `uuid` twice yields one logical effect.
- **Polling parity:** the Events endpoint returns the same events; `dispatched=false` filter returns only new ones; reading flips the flag.
- **Action lifecycle:** a requested action auto-creates a `queued` log; integration PATCHes `in_progress → completed` with a human-readable `status_message`; a forced failure emits a notification under the §6 conditions.
- **Heartbeat:** absent heartbeats flip the health indicator stale within the expected window.
- **Tenant isolation:** a token for org A cannot read org B (RLS); API token is Admin-only.
- **DACH:** money fields carry explicit currency + minor units; DATEV export action produces a valid DATEV artifact; e-invoice export archived per GoBD; all API traffic stays in the EU region.
- **Safety:** no API path mutates ACLs, hard-deletes, or moves funds.

**Sources:** `integration-development-guide`, `paperless-parts-streaming-api`, `integration-manager`, `integration-actions`, `autodesk-fusion-integration` (all in `paperless-parts-kb-reference/`); cross-refs `DOMAIN-MODEL.md`, `DB-SCHEMA.sql`, `DACH-DELTA-LAYER.md`, `AI-LENS-ENGINE-SPEC.md`, `DECISIONS.md`.
