# UI Prototype — input brief for the `/prototype` session

**Purpose:** a **throwaway, clickable** prototype to validate UX and screen flow before the real build. Not production code — do not optimize for reuse. A later session rebuilds validated screens in the real stack.

**How to run it:** start a **separate** session, invoke `/prototype`, and feed it the inputs below. Keep the scope tight — prototype the core quoting flow first, not all 20+ screens.

---

## Feed these files (in priority order)

**1 — Start from the existing mock (the seed):**
- `../docs/analysis/ui/BidFactory-LiveMock.html` — the current live mock; the prototype's visual + interaction starting point.

**2 — Real screens with real labels (highest-fidelity reference):**
- `../docs/reference/screenshots/` — actual Paperless Parts screens (dropdown labels, field names, table columns).
- `../docs/reference/Screenshot-Mapping.md` — the legend tying each screenshot to a spec section. Use this to find the right screenshot for a screen.

**3 — What each screen must contain (spec):**
- `../docs/spec/SPEC-INDEX.md` — jump map. Pull these anchors from `Bid-Factory-Build-Spec.html`:
  - Design system / shell: `#ui-system`, `#shell`
  - Core flow: `#dashboard`, `#quoteslist`, `#quotedetail`, `#linecreate`, `#partview`, `#costing`
  - Viewers: `#cad`, `#pdf`
  - AI + rules surfaces: `#wingman` (Lens), `#rules`
  - Assemblies/BOM (if in scope): `#bombuilder`, `#assembly`, `#sheetmetal`, `#nesting`
  - Buyer-facing: `#digitalquote`, `#smart-rfq`

**4 — Flows & states (so clicks go somewhere sensible):**
- `../docs/subsystems/USER-STORIES-AND-WORKFLOWS.md` — roles, choreography, state diagrams, 23 stories.

**5 — Design direction (optional, for look & feel):**
- `../docs/analysis/ui/UI-Recommendations.html`, `UI-Research-2026.html`, `UI-Alternatives-Research.html`.

---

## Non-negotiable UX guardrails (from `docs/decisions/DECISIONS.md`)

- **AI-Governor pattern:** all Lens (AI) suggestions render **purple at ~55% opacity** until the user **explicitly Accepts**. Never show AI output as already-applied.
- **Naming in UI copy:** AI layer = **Lens**, pricing formula language = **Kalk**, advisory chat = **Tolera Advisor**, fastener sourcing = **Tolera Source**.
- **German-first UI**, metric-native (mm / kg / deg), money as **EUR** in de-DE format (`1.234,56 €`; CH `CHF 1'234.56`).
- **Digital quote is fully white-label** — org logo/brand colours, no Tolera branding visible to the buyer.
- Auth: password-primary with magic-link fallback (Clerk); Google/Microsoft SSO.

## Suggested prototype scope (first pass)

Estimator happy path: **Dashboard → Quotes list → Quote detail → add line item (upload) → Part estimating view (geometry + DFM + Lens findings) → Costing/pricing → send digital quote.** Add BOM/assembly + sheet-metal/nesting as a second pass only if needed.
