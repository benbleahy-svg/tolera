# Würth ("Tolera Source") adapter fixtures — the contract

M6.7. `catalog.json` is a **recorded response**, and it is the contract the live
Würth endpoint is expected to conform to. Building against it is the decided
posture — `DECISIONS.md` 2026-06-14 *Würth API access*: "Build adapter against a
fixture response (documented JSON schema). Real credentials slot in without code
changes. Do not block M6 on Würth procurement." The swap is config only
(`WUERTH_MODE=fixture|live`), never a code change.

Naming: the supplier surface is **Tolera Source** in all UI copy
(`DECISIONS.md` 2026-06-19 *Partner integration names*); "Würth" appears only in
config keys and the adapter class.

## 1. Availability + pricing — response (`catalog.json`)

```jsonc
{
  "schema_version": "1.0",
  "supplier": "wuerth",
  "currency": "EUR",              // ISO-4217; every price below is in this currency
  "items": [
    {
      "oem_part_number": "0057 8 30",   // lookup key (matched case/whitespace-insensitively)
      "description": "Sechskantschraube DIN 933 M8x30, verzinkt",
      "brand": "Würth",
      "unit": "piece",
      "quantity_available": 12500,      // distributor stock at query time
      "lead_time_days": 2,
      "price_breaks": [                 // ascending min_quantity; the first break must be 1
        { "min_quantity": 1,    "unit_price_minor": 24 },
        { "min_quantity": 100,  "unit_price_minor": 19 }
      ]
    }
  ]
}
```

**Money.** `unit_price_minor` is an **integer in minor units** (EUR cents) and is
always read together with the response `currency` — never a float, never a bare
number (CLAUDE.md §5). No FX conversion happens anywhere: the supplier's quoted
currency is reported verbatim, and a CHF shop sees an EUR-labelled supplier price.

**Availability semantics** are computed by the adapter, not the supplier: per
requested quantity break, stock ≥ **200 %** of the required quantity is
`available` (🟢), stock ≥ 100 % is `at_risk` (🟡), otherwise `insufficient` (🔴).
That is the reference product's inventory-dot rule (spec `#collab` → "Real-time
purchased-component pricing & availability").

**Unknown part numbers** are not an error: the item is simply absent from
`items`, and the adapter reports `found: false` for it.

## 2. Sourcing RFQ — request (what the adapter *sends*)

There is no fixture file for this: the assertion is on the **request shape** the
adapter produces (block AC — "an RFQ-send through the adapter produces the
documented request shape"). It is covered by `tests/test_sourcing_m67.py`.

```jsonc
{
  "schema_version": "1.0",
  "supplier": "wuerth",
  "reference": "TS-RFQ-3f1c…",       // Tolera-side idempotency key, echoed back
  "requested_by": "Fechner GmbH",     // org display name — no personal data
  "reply_to": "einkauf@fechner.de",   // optional; omitted when not supplied
  "message": "Bitte Preis für Serie 2026",
  "lines": [
    { "oem_part_number": "0057 8 30", "description": "…", "quantities": [100, 500] }
  ]
}
```

Response: `{ "reference": …, "accepted": true, "supplier_reference": "WUE-…",
"estimated_response_hours": 24 }`.

**No files are ever attached.** This lane carries part numbers and quantities
only, so the mandatory external-send gate (per-send confirmation + redacted
variant + export-control screening) does not apply — that gate belongs to
M6.7c's `PartQuotingAdapter`, where customer CAD leaves the tenant
(`DECISIONS.md` 2026-07-07 *CNC part quick-quote adapter*).

## 3. Live mode

`WUERTH_MODE=live` additionally requires `WUERTH_BASE_URL` and `WUERTH_API_KEY`
(`app/config.py` → `validate_wuerth()`, called at app start). It fails closed:
live mode without a key raises at boot rather than degrading silently. No
credential is ever hard-coded, logged, or returned to a client.
