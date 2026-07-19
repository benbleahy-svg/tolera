# HubSpot CRM fixture — the adapter contract (M6.8)

`crm.json` is a **recorded HubSpot CRM v3 response**, and it *is* the contract
the `HubSpotCrmAdapter` is built against. Mock-first is the committed adapter
posture for every external connector (build-plan M6; `DECISIONS.md` — adapter
pattern): the adapter runs against this document until real credentials land,
and promoting to the live endpoint is **config only** — no code change.

```
HUBSPOT_MODE=live
HUBSPOT_BASE_URL=https://api.hubapi.com
HUBSPOT_API_KEY=<private-app token>
```

`Settings.validate_hubspot()` fails closed: `live` without a base URL or token
raises at boot rather than degrading every sync into a silent "CRM unavailable"
that looks like an outage.

> The **free** HubSpot tier has no API access (spec `#crm`), which is why the
> reference product steers customers to CRM Starter. A live promotion therefore
> needs a paid portal, not just a token.

## 1. Response schema (`fetch_crm`)

```jsonc
{
  "schema_version": "1.0",
  "portal_id": "<string>",
  "results": {
    "companies": [ { "id": "<string>", "properties": { … } } ],
    "contacts":  [ { "id": "<string>", "properties": { … } } ]
  }
}
```

Companies and contacts are read with an explicit `properties` projection, so the
live client requests exactly the keys below and nothing else.

| Object | HubSpot property | → Tolera field | Notes |
|---|---|---|---|
| company | `name` | `account.name` | Required; a nameless company is dropped |
| company | `email` | `account.email` | |
| company | `phone` | `account.phone` | |
| company | `domain` | `account.website` | Bare domain on the wire; `https://` added on read, stripped on write |
| company | `hs_lastmodifieddate` | *(reporting only)* | **Never** used for conflict resolution — see §3 |
| contact | `email` | `contact.email` | Required; an email-less contact is dropped |
| contact | `firstname` / `lastname` | `contact.first_name` / `last_name` | |
| contact | `phone` | `contact.phone` | |
| contact | `associatedcompanyid` | `contact.account_id` | Resolved via the parent's `external_crm_id`; unresolvable ⇒ left NULL (account-less contacts are legal, M1.1) |

HubSpot writes `null` rather than omitting a property; `_prop()` treats `null`
and `""` alike as absent.

## 2. Write shape (`upsert`)

```jsonc
{ "id": "<external id, omitted to create>", "properties": { … } }
```

* `POST /crm/v3/objects/{type}` to create, `PATCH …/{id}` to update.
* **Absent keys are omitted, never sent as `null`.** HubSpot reads an explicit
  `null` as "clear this field", so sending one for a value Tolera simply does
  not hold would *erase* CRM data — the one way a "Tolera wins" sync could
  still destroy something it does not own.

### Deal (`deals`) — the advanced tier

Written on `quote.sent` (spec `#crm`: "PP writes the quoted dollar amount back
to the deal so the HubSpot pipeline stays live").

| Property | Source |
|---|---|
| `dealname` | `Angebot <quote.number>` |
| `amount` | quote net as a **decimal string** — converted from integer minor units at the client seam |
| `deal_currency_code` | `quote.currency` (EUR/CHF) |
| `tolera_quote_id` | `quote.id` — the back-reference that makes the link two-way without a join table |

The returned id is stored on `quote.crm_opportunity_id`, so a re-send updates
the same deal instead of creating a second one.

**Money.** Everything inside Tolera is integer minor units + an explicit
currency (`CLAUDE.md` §5). HubSpot's decimal string is converted in
`_amount_to_minor` / `_minor_to_amount` and nowhere else, so no float ever
reaches the domain.

## 3. Conflict resolution — Tolera always wins

`DECISIONS.md` 2026-07-17 ("HubSpot CRM conflict") fixes v1 as
**Tolera-always-wins**, with no field-level merge; field-level resolution is a
post-pilot upgrade.

The rule keys on Tolera's own `last_synced_at` watermark, **not** on
`hs_lastmodifieddate`. Two reasons: the clocks are unrelated, and HubSpot bumps
its own timestamp on writes *we* caused, so a clock comparison would make the
sync fight itself.

```
inbound applies  ⟺  updated_at <= last_synced_at
                    (nobody edited the Tolera row since the last sync)
```

* never synced → create; nothing to conflict with
* synced, untouched → the CRM is the only side that moved: apply
* synced, then edited in Tolera → both moved ⇒ **refuse the inbound write** and
  report it as `conflict_tolera_wins` (reported, not swallowed, so the action
  log names the diverged records)

Outbound pushes are unconditional by the same rule: Tolera is the system of
record, so its value overwrites the CRM without asking.

## 4. Safety

The adapter exposes reads and upserts only. There is no path to alter
sharing/permissions/ACLs, hard-delete a record, or move funds
(`INTEGRATION-API-CONTRACT` §5). That is enforced twice, independently: the
interface has no such method, and `app.integration_actions.assert_permitted`
rejects any action *type* that names one of those operations before a log row is
even created.
