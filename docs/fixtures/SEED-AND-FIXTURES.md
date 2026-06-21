# Seed Catalog & Golden-Fixtures Harness

**Status:** Build-readiness appendix for Tolera (Bid Factory). Closes Gap-Audit §5 (the #1 blocker: "no seed data manifest, no fixtures, no golden outputs"). **Two parts:** (1) the **seed catalog** that provisions a new org's Configure data; (2) the **golden-fixtures harness** that lets the three engines be verified end-to-end. Companion: `seed.skeleton.json` (loadable structure), `DB-SCHEMA.sql`, the three engine specs.

> Per `DECISIONS.md`: pilot org slug **`fechner`**; 5–10 anonymised Fechner RFQ fixture packages arrive **~2026-06-23**. Build the harness structure now; slot fixtures in on delivery.

---

## Part 1 — Seed catalog (org provisioning)

A new org is provisioned from a single idempotent **`seed.json`** (one per org; re-runnable). Sections:

### 1. Org + identity
- `organization`: Fechner — `slug=fechner`, `country=DE`, `currency=EUR`, `locale=de-DE`, `default_tolerance_class=ISO 2768-m`, `export_regime=eu_dual_use`, white-label `brand`.
- `users` + `user_org_memberships` (admin + estimators/salespeople); ingest address `fechner@rfq.tolera.eu`.

### 2. Materials tree (DACH DIN/EN)
- **Classes:** Metal, Polymer, Composite, Sand, Wax, Additive.
- **Families/materials** keyed on **Werkstoffnummer** + EN name + AISI alias, e.g.:
  - `1.4301` / X5CrNi18-10 / 304 (stainless); `1.4404` / X2CrNiMo17-12-2 / 316L.
  - `1.0038` / S235JR / A36 (structural steel); `1.0570` / S355J2.
  - `EN AW-6061` / 3.3211 / 6061; `EN AW-5083` / 3.3547.
  - `3.7035` Ti Grade 2; plus polymers (POM, PA6, PEEK).
- Each carries `density`, `cost_per_volume`/`cost_per_area`, `added_lead_time_days`.

### 3. Operation library (54 pre-installed)
Schema per op: `name`, `category` (operation|material), `calc_mode`, rate config, `surcharge_pct` (default 0), `is_outside_service`, `is_finish`. **31 Machine+Operator + 23 Labour-Only**, German names, covering CNC machining, sheet metal, welding/joining, surface finishing, additive, assembly, logistics/QC. (Full 54 list lives in the spec's **Operation Library** section — that is authoritative; seed mirrors it.) Representative entries: `CNC Mill`, `CNC Lathe`, `Drill Press`, `Laser`, `Punch`, `Forming`, `Bürsten` (brushing/deburr), `Roboterschweißen` (robotic weld), `Deburr` / `Deburr-CNC`, `Hardware Insert`, `Material | Bar (Round/Rectangular/I-Beam)`, `Material | Sheet (Nesting)`, `Engineering`, `QC`, `Pack & Ship`, `PC Piece Price`, `Outside Service | General`.
- **Auto-save:** a custom op added inline on a quote is saved to the org library for reuse.

### 4. Processes + routers
- Core-4 process templates (Sheet Metal, Milling, Lathe, Tube Laser) each with a default router (ordered `process_operation` rows, flags: per_setup / is_assembly / root_component_only) + an attached default interrogation + auto-routing formula.
- **`Assembly | Parent-Level`** process — default router = `Assembly | Manufactured` + `Generic | Shipping Prep` (always-needed on assembly roots); Hardware Install / Weld in library but **not** auto-added.
- **Default purchased-component process** (single op reading `piece_price`).
- Per-process `available_in_smart_rfq` toggle + `external_name`.

### 5. Default interrogation profiles
One `custom_interrogation` per Core-4 family seeded with the **default thresholds/toggles from `DFM-WARNINGS.md`** (e.g. "Default Sheet Metal (Laser)" with `is_laser=true`, bend-radius min 0.75×t / max 150×t, close-cutouts 1.0×t, …). Material-specific variants optional.

### 6. Pricing defaults
- **Pricing items:** standard markup/margin per category (general/material/inside/outside/purchased_component) + the **Zuschlagskalkulation** seed (overhead surcharge) from the spec.
- **Discounts:** sample account/volume discount (Kalk).
- **Add-ons:** NRE / tooling / minimum-order examples.
- **Expedite options** default set (days_faster + markup_pct) + lead-time display units.

### 7. Workflow + rules + output
- **Workflow steps:** default set (Not Started → In Progress → On Hold → Completed, + No Quote) — or a custom multi-step set (e.g. Estimate → Review → Approve).
- **Starter rule library** (from `building-review-rules`): e.g. *export-control flag detected → require manager review*; *no material specified → block send*; *tight tolerance (≤ X) → flag for senior estimator*; *over-budget margin → review*. Each = signals + filters + resolution options.
- **Custom tables:** seed `material_inventory`, `laser_cut_rates`, `punch_tooling` examples (used by Kalk `table_var`).
- **Email templates** (German): quote-sent, RFQ-received, follow-up. **Quote display settings** (white-label, EUR, net + MwSt).

### Seed mechanics
- Idempotent upsert keyed on (org, natural key). One command provisions a demo/pilot org (the spec's "seed script"). Use it for **tests** (each test run seeds a clean org) and **first-run** (Quick Setup pre-fills from it).

---

## Part 2 — Golden-fixtures harness

```
/fixtures
  /cad/            # STEP / SLDPRT / DXF / STL — Core-4 + assembly samples
  /drawings/       # PDF prints with GD&T (+ a scanned one for OCR)
  /email/          # one realistic RFQ .eml with attachments (+ a PDF-as-ZIP, a 3D-PDF)
  seed.json        # the Part-1 catalog the goldens assume
  /golden/
    <fixture>.interrogation.json   # expected AnalysisResult
    <fixture>.extraction.json      # expected Lens findings
    <fixture>.pricing.json         # expected unit/total price per quantity
    <fixture>.bom.json             # expected BomNode tree (assemblies)
```

**Golden schemas (bind to the engine specs):**
- **Interrogation** (`INTERROGATION-ENGINE-SPEC §2`): e.g. sheet-metal STEP → `{bend_count:3, thickness:0.74mm, size_x, size_y, pierce_count, total_cut_length, features[…]}`; mill → `{setup_count, runtime, confidence}`; assert within tolerance.
- **Extraction** (`AI-LENS-ENGINE-SPEC §8`): print → `{part_number, revision, material(DIN), units:mm, holes[…], control_frames[…], tolerances[…]}`; assert value + confidence; **never-hallucinate** check.
- **Pricing** (`PRICING-ENGINE-SPEC §3/§7`): part + router + qty breaks → `{unit_price, total_price}` per quantity; assert exact (the verified demo numbers + Fechner cases); margin/markup unit tests.
- **BOM:** assembly PDF/CAD → expected multi-level tree (parts, nodes, quantities); repeat-part → single shared component + correct make-qty.

**Harness behavior:**
- A test runner seeds a clean `fechner`-like org from `seed.json`, ingests each fixture, runs interrogation + extraction + pricing, and diffs outputs against `/golden`.
- Numeric asserts use tolerances (geometry) or exact (pricing) per the spec.
- Wire to the milestone acceptance criteria (the spec's M1/M4 already reference "fixture sheet-metal STEP → bends/thickness/flat vs goldens; nest math vs hand-calc; fixture assembly PDF → published BOM").

**Now vs on-fixture-delivery:**
- **Now:** build `/fixtures` layout, `seed.json` (Part 1), golden schemas, and the runner with 1–2 synthetic/open STEP+PDF samples so the pipeline is testable.
- **On 2026-06-23:** drop in the 5–10 anonymised Fechner packages + author their goldens.

**DACH:** materials in DIN/EN; dims in mm; prices in EUR; one **CH** fixture (CHF, 8.1% VAT, QR-bill) to exercise the region path.

**Open items to log in `DECISIONS.md`:** exact 54-op rates (shop-specific), the starter rule set Fechner wants, and which fixtures cover which Core-4 family.
