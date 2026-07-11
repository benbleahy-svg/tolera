# 05 — Content EN (`/en/` mirror, final)

Translation register: professional, plain, sentence case. Same structure/IDs as `04-CONTENT-DE.md`; German is the source of truth — if the two diverge, fix EN. Constants:

- CTA-primary: **Start for free**
- CTA-secondary: **Take the product tour**
- CTA-micro: *14-day full access · no credit card · GDPR-compliant*
- Trust strip: *Data hosted in Germany* `TBD(hosting-region)` · *GDPR & DPA included* · *XRechnung & ZUGFeRD ready* · *Metric-native, DIN/EN materials*
- CTA-BAND: H2 **Your first quote in 15 minutes.** Sub: *Start with a real RFQ from your inbox — not with an implementation project.*

---

## P1 Home

**P1-hero**
- H1: **Quote parts in minutes. Not days.**
- Sub: Tolera reads your RFQ emails, analyzes the CAD geometry, and prices with your own logic — from inquiry to send-ready quote in under 15 minutes. Built for custom manufacturers in Germany, Austria, and Switzerland.

**P1-thread** — H2: **What happens to an RFQ inside Tolera**
1. **Email in.** Forward the inquiry to `your-shop@rfq.tolera.eu` — draft quote, contact, and attachments are ready.
2. **Lens reads along.** Line items, quantities, materials, tolerances — extracted from email and drawing, always as a suggestion with its source.
3. **Geometry understood.** STEP file in; dimensions, volume, bends, machined features out — plus DFM warnings.
4. **Kalk does the math.** Your costing logic as readable formulas, per quantity — no black-box price.
5. **Quote out.** Digital quote or A4 PDF with correct VAT. Your customer orders online.

**P1-bento** — H2: **Everything between inquiry and order.**
- Quoting (large): **Costing that carries your handwriting.** Quantity breaks, margins per cost category, approval stages — and formulas you can edit yourself.
- Geometry (large): **The machine sees the part.** Automatic geometry analysis for milling, turning, sheet metal, and tube — with manufacturability warnings before they get expensive.
- Lens: **Drawings that read themselves.** Lens finds tolerances, finishes, and cert requirements — and shows you where they're written.
- Requirements review: **Nothing slips through.** Rules check every RFQ for critical requirements — automatically.
- Digital quote: **Quotes that get ordered.** Online quote with quantity selection and checkout via PO, SEPA, or Swiss QR-bill.
- File formats: **STEP, JT, DXF, PDF, and more.** `mono: .step .stp .jt .stl .3mf .dxf .dwg .pdf` — up to 200 MB per file. `TBD(format-tier)`

**P1-dach** — H2: **Built for the DACH region. Not translated into it.**
Intro: Software for German, Austrian, and Swiss manufacturers has to do more than speak German.
- **EUR & CHF, VAT & reverse charge.** Prices in your currency, tax under your law — DE 19%/7%, AT 20%, CH 8.1%.
- **E-invoicing out of the box.** XRechnung, ZUGFeRD, ebInterface, QR-bill — ready for the mandates.
- **Material numbers, not conversions.** 1.4301 is 1.4301 — DIN/EN materials, metric, no inch detours.
- **GDPR, GoBD, EU export control.** DPA included, audit-proof retention, dual-use per EU law — not ITAR.

**P1-selfserve** — H2: **No implementation project. No sales call.**
Intro: The established systems take weeks to months of guided onboarding by an implementation team. You set Tolera up yourself — today.
- **Start today.** Sign up, describe your shop, upload a real RFQ. No appointment, no waitlist.
- **Your logic, edited by you.** Kalk formulas are readable and changeable — you don't need a consultant to update an hourly rate.
- **Help in German or English, when you want it.** Documentation, examples, and support — optional, never mandatory.
- Link: *How this compares to Paperless Parts →* `/en/compare/paperless-parts`

**P1-case** — H2: **In production at Fechner.** `TBD(fechner)` — quote placeholder as in DE.

**P1-faq**
1. **What does Tolera cost?** There's a permanently free plan with 5 quotes per month. Paid plans start at `TBD(price-starter)` € — all prices are public on the [pricing page](/en/pricing).
2. **Which file formats does Tolera understand?** STEP and JT with full geometry analysis; STL/3MF as mesh; DXF, DWG, and PDF for 2D drawings. `TBD(format-tier)` Up to 200 MB per file.
3. **Where is our data stored?** In Germany `TBD(hosting-region)`, GDPR-compliant, with a data processing agreement. Your drawings never train third-party AI models.
4. **How long does setup take?** Sign-up to first priced quote: under 15 minutes with a real RFQ. You fine-tune your costing logic afterwards — while already working.
5. **Does Tolera replace our ERP?** No. Tolera owns the path from inquiry to order; orders and documents hand over to your existing system.

---

## P2 /en/product/quoting

**P2-hero** — H1: **Costing that carries your handwriting.** Sub: Quantity breaks, margins per cost category, approval workflows — and a formula language your estimator can actually read. Tolera prices the way your shop does, just faster.

**P2-workflow** — H2: **From draft to order — one pass.** RFQ becomes a draft quote → price line items (per quantity, with win likelihood) → review by sales, engineering, purchasing, or management — whatever your rules require → send → the customer picks quantity and lead time and orders. Override any calculated value by hand — recalculation never destroys your input.

**P2-kalk** — H2: **Kalk: formulas, not a black box.** Your costing logic as short, readable formulas — setup time, run time, material, overhead. You see every number and how it was computed. Change an hourly rate yourself, without a ticket or a consultant. *(Same code sample as DE, comment line: "Example — your formulas belong to you.")*

**P2-outputs** — H2: **Quotes that get ordered.** Digital quote: your customer opens a link, sees prices per quantity and lead-time option, and orders — via PO number, SEPA, or Swiss QR-bill. Or classic: an A4 PDF with your logo and correct tax. XRechnung and ZUGFeRD are ready when your customers require e-invoices.

**P2-review** — H2: **Four eyes where it matters.** Approval stages for sales, engineering, material, outside services, and management — configurable, logged, no email ping-pong.

**P2-faq**
1. **Can we reproduce our Excel costing?** In most cases, yes — Kalk covers setup/run times, material, surcharges, and quantity breaks. You port your logic formula by formula and check results against real past quotes.
2. **What about material price changes?** Material prices are maintained centrally `TBD(wuerth-live)`; new costings always use the current value. Existing quotes stay untouched.
3. **Can I override prices manually?** Yes, any value. Tolera stores the calculated and the manual value separately — nothing is lost.

---

## P3 /en/product/geometry

**P3-hero** — H1: **The machine sees the part.** Sub: Upload a STEP file, wait seconds: dimensions, volume, bends, machined features — and manufacturability warnings before you price.

**P3-interrogation** — H2: **What Tolera reads from geometry.** Per manufacturing process, Tolera extracts the values your costing needs: `mono-chips: dimensions (mm) · volume (cm³) · surface area (cm²) · sheet thickness · bends (count/angle) · holes & pockets · thread candidates · stock suggestion` — automatically, per part, ready for costing.

**P3-dfm** — H2: **See problems before they get expensive.** Thin walls, over-deep pockets, critical bend radii, unreachable features: Tolera warns at upload — not on the shop floor. Every warning points to the exact spot in the 3D model.

**P3-viewer** — H2: **View, measure, section.** 3D viewer in the browser: rotate, measure, add section planes, pick faces. Next to it, the drawing viewer for PDF and 2D — with annotations for your team.

**P3-files** — H2: **Your files, as they arrive.** `mono: STEP / STP / JT` — full analysis. `mono: STL / 3MF / OBJ` — mesh view. `mono: DXF / DWG / PDF / TIFF` — 2D & drawings. `TBD(format-tier)` Up to 200 MB per file, ZIP packages for assemblies, multi-level BOMs from PDF tables.

**P3-faq**
1. **Do we need special CAD software?** No. Tolera analyzes the files your customers already send — in the browser, nothing to install.
2. **How accurate are the extracted values?** Geometry values come straight from the CAD model (B-rep analysis), not from an estimate. What the model doesn't contain, Tolera doesn't invent.
3. **What about assemblies?** Upload a ZIP — Tolera detects the structure, builds the BOM, and analyzes every component.

---

## P4 /en/product/lens

**P4-hero** — H1: **Lens reads your RFQs. You decide.** Sub: Emails, drawings, BOMs: Lens extracts line items, tolerances, and requirements — as suggestions with sources, never as silent decisions.

**P4-ingest** — H2: **The inbox that works with you.** Every inquiry sent to `mono: your-shop@rfq.tolera.eu` becomes a draft quote: contact matched or created, attachments saved, line items and quantities pre-filled. Replies continue as a thread — nothing stays buried in a personal mailbox.

**P4-extract** — H2: **Drawings that read themselves.** Lens finds in prints and PDFs: tolerances and fits, GD&T, surface finishes, heat treatment, coatings, certification requirements. Grouped by category, every finding clickable down to its location in the document.

**P4-rules** — H2: **Requirements review: nothing slips through.** Build rules from building blocks — geometry, drawing text, GD&T, file type, quote data: "If a 3.1 certificate is required → create a review task for purchasing." "If tolerance tighter than IT7 → engineering must approve." Every RFQ runs through the same review — even at 5 pm on a Friday.

**P4-trust** — H2: **AI that suggests — and never decides.** Everything Lens finds remains a suggestion until a human accepts it. No Lens value ever flows unreviewed into a price. What isn't on the drawing doesn't get invented. Processing is GDPR-compliant in the EU `TBD(ai-routing)`; your drawings never train third-party models.

**P4-faq**
1. **What if Lens misreads something?** Reject the suggestion — one click. Only what you confirm is accepted, and every finding shows its source.
2. **Does it work with scanned drawings?** Printed and scanned drawings yes, within limits `TBD(scan-limits)`. The better the original, the more complete the findings — missing data stays empty instead of being guessed.
3. **Does Lens read purchase orders and BOMs?** Yes — BOM tables from PDFs become an editable, multi-level bill of materials.

---

## P5–P8 Industry pages

Mirror the DE structure with head terms: **CNC machining quoting software** (P5) · **Sheet metal quoting software** (P6) · **Tube laser quoting software** (P7) · **Turned parts quoting software** (P8). Translate pains/features/specifics/FAQ 1:1 from `04-CONTENT-DE.md`; keep mono chips metric (mm/kg — do not convert to inches; metric-native is the brand).

---

## P9 /en/pricing

**P9-hero** — H1: **Pricing. Public.** Sub: No "contact us for pricing" games. Every plan is listed here — test for 14 days with full access, no credit card.

**P9-tiers** — Free — €0 — *To keep in your pocket.* 5 quotes/month · 1 user · geometry analysis & viewers · digital quote. — Starter `TBD(price-starter)` — *For getting into the routine.* — Growth `TBD(price-growth)` — **Recommended** — *For shops quoting at full clip.* — Enterprise — on request — multi-site/orgs, SSO `TBD(sso-tier)`, custom DPA/SLA. Toggles: EUR/CHF · monthly/annual (*save `TBD(annual-discount)`%*).

**P9-trial** — H2: **14 days. Full access. No credit card.** The trial ends automatically — no silent subscription, no notice period. Then you decide: free plan or upgrade.

**P9-faq**
1. **How does VAT work?** Billing runs through Paddle as merchant of record: with a valid VAT ID, reverse charge applies; otherwise your country's VAT is added. You always receive a compliant invoice.
2. **Can we pay in CHF?** Yes — pricing and billing in CHF for Swiss shops.
3. **How do I cancel?** Anytime, effective end of the billing period, directly in the app. No calls, no forms.
4. **What happens to our data after cancellation?** You export your data yourself `TBD(export-scope)`; afterwards it is deleted per the DPA retention terms. GoBD-relevant documents remain exportable.
5. **Is there a data processing agreement (DPA)?** Yes, by default, signable digitally `TBD(avv-process)`.
6. **Is annual billing worth it?** Annual saves `TBD(annual-discount)`% versus monthly.

---

## P10 /en/tour
H1: **Watch Tolera work. Two minutes, no sign-up.** Steps: `08-TOUR-SPEC.md` (EN column). Summary: *You've seen: an email became a draft quote · the geometry was analyzed automatically · the price came from readable formulas.*

## P11 /en/compare/paperless-parts
H1: **Tolera vs. Paperless Parts.** Intro, table, "When Paperless Parts is the better choice," and "Test in parallel, risk-free" — translate 1:1 from DE, same footnote sources, same `TBD(pp-verify-date)`.

## P12 /en/company
H1: **Quoting is the owner's job. Too often literally.** Mission, founder `TBD(founder-bio)`, Fechner block, contact — translate 1:1.

## P13 Legal (EN)
`/en/imprint`, `/en/privacy`, `/en/terms` — convenience translations with the notice: *"This English version is provided for convenience. The German version is legally binding."*

## 404
H1: **This page doesn't exist.** Sub: One of these might help: [Home](/en/) · [Product tour](/en/tour) · [Pricing](/en/pricing).
