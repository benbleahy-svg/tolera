# Self-Serve Onboarding — Research & Design
**For:** Bid Factory (DACH manufacturing CPQ) · **Date:** 2026-06-13
**Goal:** self-serve signup from the website (HubSpot-style), AI does the setup, first win ASAP, human check-in layered on top.

---

## Part 1 — What the research says

### The market is barbelled, and the middle is empty

Incumbent onboarding is a services project: **Paperless Parts takes 8–12 weeks**, with a 3-person implementation team and PP staff writing the customer's pricing logic (P3L) *for* them; customers spend 4–8 hrs/week in meetings + homework ([PP implementation page](https://www.paperlessparts.com/implementation-and-onboarding/)). No trial, no published pricing — and shop owners on Practical Machinist self-disqualify before ever seeing a demo ("ONE MEELLION DOLLARS to set it up", [thread](https://www.practicalmachinist.com/forum/threads/what-is-the-deal-with-paperless-parts.431259/)). Lantek, WICAM, JobBOSS², CADDi: all sales-led, all setup-heavy.

The self-serve challengers are thin but prove the mechanics work in this exact market:

| Product | Self-serve mechanic | Numbers |
|---|---|---|
| **Spanflug Make** (DACH, CNC) | **Zero-config start** — ships with a market-calibrated default price algorithm; shops adjust later. **5 parts/month free forever** + 14-day full trial | ~€300/mo entry ([source](https://www.mikutec.ch/software-kostenkalkulation-spanflug-fuer-fertiger/)) |
| **Tempus ToolBox** (laser) | 14-day trial, no credit card, guided first-login tour | Setup "under 30 min", from ~$100/mo ([source](https://tempustools.com/pricing/)) |
| **DigiFabster** | 7-day trial "no sales call"; pre-built machine/material templates; **AI price calibration: upload ≤10 old parts + your real prices → system auto-tunes rates to reproduce them** | Calibration "30 minutes vs days" ([source](https://digifabster.com/product/train-your-quote-engine-like-youd-train-a-new-estimator/)) |
| **Stella Source** (sheet metal) | Free tier + first-run wizard: machine wattage → tech table → rates → margin | "Reasonable quote out the door quickly" ([Fabricator](https://www.thefabricator.com/thefabricator/article/cadcamsoftware/metal-fabrication-quoting-startup-lowers-the-barrier-to-entry)) |

**Nobody combines deep CPQ configurability with LLM-led setup.** DigiFabster's calibration is the only AI prior art, and it's a feature, not an onboarding. That lane is open.

### What 2026 onboarding looks like outside this vertical

ProductLed's maturity model — **Inform → Guide → Execute → Orchestrate** — captures the shift: stop educating the user about the UI, start having the agent *do the setup from the user's own data*. Bar for AI-native products: value in ~60 seconds, low input → great output ([ProductLed](https://productled.com/blog/ai-onboarding)). Concrete patterns:

- **Scrape-to-configure:** Relay.app asks for your LinkedIn URL mid-signup and personalizes everything from it; Firecrawl powers many "enter your URL, we pre-fill your account" flows. → Validates the "scrape the shop's website" idea.
- **Generate the first artifact:** Gamma builds your first full deck seconds after signup — kill the blank state with the user's own output, not demo data ([Appcues aha-moment guide](https://www.appcues.com/blog/aha-moment-guide)).
- **Shrink the quiz:** Notion cut onboarding to **one question** and infers the rest. HubSpot's lesson isn't 22 questions — it's branching infrastructure so each persona answers only what's needed ([HubSpot signup architecture](https://product.hubspot.com/blog/signup-architecture)).
- **Checklists barely work alone:** median completion 10% ([Userpilot benchmark](https://userpilot.com/blog/onboarding-checklist-completion-rate-benchmarks/)). Keep one, keep it to 3 items, anchor it to real value.
- **Conversational/voice:** the best-documented case (Cor's screen-aware voice agent "Obi") shows users treat it like an always-available CSM: 87% of questions resolved without escalation, 50% of users skip ahead, 38% open with their own question ([data](https://www.growthmates.news/p/voice-ai-for-onboarding-what-the)). Evidence supports **text-first conversational with voice opt-in** — not a mandatory voice wizard.
- **Hybrid wins in B2B:** automation + human check-in scores 73% satisfaction vs 41% digital-only ([benchmark](https://www.saashero.net/customer-retention/b2b-saas-conversion-benchmarks-journey/)). Your "salesperson checks in" instinct is right — schedule it as a feature, not a fallback.

### Benchmarks to hold ourselves to

Median SaaS activation ~25–34%; top quartile ≈ 2.3× median ([Lenny's](https://www.lennysnewsletter.com/p/what-is-a-good-activation-rate)). PLG time-to-value target: **first value < 15–30 min**, first wow < 60s. TTV under 7 days correlates with ~50% lower churn. The DACH reference experience is 247TailorSteel's Sophia: **STEP file → price in under 1 minute** — your buyers' customers already know this is possible.

### DACH-specific cautions

German Mittelstand blockers are **skills and skepticism, not willingness**: show value with *their* data before asking for commitment; trust signals early (data-in-Germany, GDPR/DPA, references from similar shops, German UI); no credit card for trial. And the **documented churn trigger** for self-serve quoting tools is one absurd price in the first session ([DigiFabster review: "$4,900 for a simple plate"](https://www.softwareadvice.com/manufacturing/digifabsterquickquote-profile/)) — pricing-confidence guardrails are not optional.

---

## Part 2 — The Bid Factory onboarding design

### North star

> **Activation event: the user turns one of their own RFQs into a priced quote in the first session** (target < 15 min from signup), and sends a quote within 7 days.

Two engineered moments:
1. **The 60-second wow** — "it already knows my shop" (website scrape → shop profile cards).
2. **The first win** — their own RFQ, parsed, configured, priced, on screen.

### The core mechanism: the Setup Interview (decided)

**Principle: anything personal to the business is collected by an AI agent in conversation — once, correctly — and the agent inputs all the data itself.** Scraping handles public facts; defaults handle what the user doesn't know; but rates, margins, and policies are *asked*, because they're personal to each shop and we want to do the work right once. The user never fills an empty form.

**Format:** a 5–10 minute structured conversation (text chat by default, voice opt-in — same agent either way), immediately after the scrape confirms the shop profile. The agent already knows the machine park and processes from Stage 1, so it asks like a consultant, not a form:

> *"Eure Website zeigt zwei TruLaser 3030. Was rechnet ihr für die Laserstunde? Üblich in der Region sind €90–110."*
> → "95" → written to the Laser machine rate, provenance = interview, done. Next topic.

**Interview design rules:**

- **Agenda visible** as progress chips (Maschinen & Sätze → Lohn/Gemeinkosten → Marge → Lieferzeiten → Material → Outside Services → Angebots-Standards) so the user sees it's bounded, skippable, and resumable.
- **Pre-seeded, never cold:** every question carries a suggested value (from the scrape, the DACH default library, or regional norms) — the user confirms, corrects, or says "weiß ich nicht" (→ default applied + flagged for the human rate review).
- **Agent executes live:** answers are written to Configure as they're spoken, with a live config-preview panel showing what's being set ("✓ Laser: €95/h · ✓ Abkanten: €70/h · Marge: 30%…"). Undo per item.
- **Hard cap ~10 min:** the agent prioritizes by pricing impact (machine rates > margin > setup times > the rest); anything not reached gets a default + lands on the "finish later" list. Quality over completeness — but what's answered is answered *right*.
- **Provenance on every value:** `interview | scraped | default | calibrated` — the human rate review and the user can always see which numbers are theirs vs assumed.
- **Transcript saved** to the org (institutional memory + the sales rep reads it before the check-in call).

**What the interview collects (the "personal data" inventory — this pattern applies beyond rates):**

| Topic | Feeds |
|---|---|
| Hourly rate per selected machine (machine park itself comes from the Stage 1.2 picker) | MachineRates, OperationDefs |
| Labor & overhead rates, typical setup times per op class | Operation cost formulas |
| Margin/markup policy (overall + per category: material, outside, purchased) | PricingItems |
| Standard lead times + expedite policy (days faster / % markup) | Lead times, Expedite defaults |
| Materials actually stocked + standard sheet/bar sizes + suppliers | Material catalog subset, nesting stock defaults |
| Outsourced operations (anodize, galvanize, heat treat…) + their vendors | OSV ops + **Vendor RFQ Portal vendor list** (two birds) |
| Quote boilerplate: T&Cs, tolerances note, validity period, payment terms, VAT setup | Quote display, templates, VAT config |
| Team: who estimates, who sells, who approves | User invites, workflow step assignees |

### Supporting layers under the interview

| Layer | What | When |
|---|---|---|
| **DACH default rate library** | Market-typical seed values per process/machine class/material/region. Role: **pre-fill for interview questions, instant fallback for skipped topics, and sanity bounds** — no longer the primary source. Clearly labeled "branchenüblich" wherever a default is live. | Day 0, under everything |
| **AI calibration ("check it against your old quotes")** | Upload 3–10 past quotes → solver cross-checks the interview rates by reproducing real prices → flags discrepancies ("your interview laser rate implies €312 for this part; you charged €280 — adjust setup time?"). Now a **validation** step, not the primary setup. | Same session or week 1 |
| **Confidence guardrails** | Interview-confirmed values price as firm; default-backed values show a **range + confidence badge** ("Richtpreis"); outlier detection (price/kg, price/cm³ bounds per process) blocks absurd outputs. **Never show one confident wrong number.** | Always |

### The flow (stage by stage)

**Stage 0 · Signup (≤60s).** Email or Google/Microsoft (Clerk). One question, asked as chips not a form: *"Was fertigt ihr hauptsächlich?"* (Blech / CNC-Zerspanung / Beides / Sonstiges) — branches the rest (HubSpot Lego-block pattern). Plus one optional field: **company website URL**. Trust strip visible: 🇩🇪 Daten in Deutschland · DSGVO · keine Kreditkarte.

**Stage 1 · The scrape (runs while they verify email, ~60–90s).** Agent scrapes the website + Impressum: company name, address, VAT-ID, logo/colors, machine park (most DACH shop sites list machines), processes/services, materials, certificates (ISO 9001…), industries served. Crossref public registries where useful. Output = a **Shop Profile** rendered as confirm/adjust suggestion cards (the same purple-suggestion pattern used product-wide):

> "Wir haben euch gefunden: *Müller Blechtechnik GmbH, Aalen* — Laserschneiden (2× Trumpf TruLaser), Abkanten, Schweißen · Stahl/Edelstahl/Alu · ISO 9001. Stimmt das?" [✓ Übernehmen] [Bearbeiten]

Each accepted card *executes setup*: org profile, facility, branding on quote PDF, process templates + default routers activated, material catalog subset, interrogation profiles, default rate library loaded for their machine classes. No website? Fall back to 3 chip-questions (processes, machine classes, materials) — still no typing.

**Stage 1.2 · Select your machines ("Maschinenpark").** A visual picker, not a text field — and the keystone inference step: **machines imply operations**, so one selection configures half of Configure.

- **Machine Catalog:** a curated, searchable database of DACH-relevant machines (brand → model → class): Trumpf/Bystronic/LVD lasers, Trumpf/Amada press brakes, DMG MORI/Hermle/Haas/Mazak mills & lathes, Index/Tornos Swiss, EDM, tube lasers, welding stations… Each entry carries: machine class, capabilities (axes, kW, bed/travel size, max sheet/bar), implied operations, implied process templates, the matching interrogation profile, and a default regional rate.
- **Pre-selected by the scrape:** machines found on the website appear already ticked ("Wir haben gefunden: 2× TruLaser 3030 ✓, TruBend 5130 ✓ — was fehlt?"). The user adds/removes via search or class tiles (Laser · Abkanten · Fräsen · Drehen · Schweißen · …). Quantity per machine. "Nicht im Katalog?" → describe it in one line, the agent classifies it into a machine class.
- **What a selection executes:** a TruBend 5130 tick creates the work center + MachineRate (default-seeded), activates Forming/press-brake OperationDefs and the sheet-metal process + DFM profile (bend warnings sized to that machine's tonnage/length), sets nesting stock constraints from bed size, and **registers the rate question for the interview**. A 5-axis mill tick activates the milling ops, the 5-axis process, the milling interrogation profile, and the complexity-indicator option.
- **Operations inferred, confirmable:** after selection, one summary card: "Daraus ergeben sich diese Arbeitsgänge: Laserschneiden, Entgraten, Abkanten, Schweißen, Versandvorbereitung… " [✓ passt] [anpassen]. Supporting ops (deburr, inspection, packing) are auto-included per process family — the user removes rather than builds.
- **Interview gets shorter and sharper:** rate questions are now per *selected machine* (not abstract op classes), in pricing-impact order — which is exactly how shop owners think about their numbers.

**Stage 1.5 · The Setup Interview (5–10 min, the heart of onboarding).** The agent says: *"Ich hab noch ein paar Fragen, die nur ihr beantworten könnt — 10 Minuten, dann rechnet das System mit euren echten Zahlen."* Then runs the structured conversation above, inputting everything itself. Skippable ("Später — erst mal ausprobieren" → defaults carry the first quote, interview nudged after), resumable, and re-runnable per topic. Done well, this is where "the work is done right once."

**Stage 2 · The first win (target: right after the interview, minute ~12–20; or minute 5 on defaults if skipped).** One screen, one prompt:

> **"Holt euch eure erste Anfrage rein."** Drag in your last RFQ — the email, the PDF drawing, the STEP file, all of it. [or: forward it to `m-blechtechnik@rfq.…` right now] [or: try a sample RFQ]

Then the product does its actual thing, narrated live by the assistant: parsing the email → extracting parts/qtys → reading the drawing (callouts found) → interrogating geometry (bends, thickness) → assigning process + router from their confirmed profile → **priced quote on screen** with the confidence-banded total. Finish with the share-worthy artifact: the branded quote PDF preview with their logo from Stage 1.

*Fallbacks:* no RFQ at hand → "forward your inbox address to yourself", sample RFQ (their branch: sheet-metal or CNC sample), or just a STEP file. Sample data is clearly marked and disposable.

**Stage 3 · Calibration cross-check (same session or nudged day 1–3).** Conversational: *"Zeig mir 3 alte Angebote — ich prüfe, ob eure Sätze stimmen."* Upload old quotes → solver reproduces their real prices using the interview rates → confirms ("passt auf ±4%") or flags specific discrepancies with a suggested fix. If the interview was skipped, this doubles as the primary tuning path (DigiFabster pattern). Every value remains editable in Configure for the power user.

**Stage 4 · Cement the habit (checklist, max 3 items).**
1. **Send your first quote** (even to yourself) — completes activation.
2. **Set up email forwarding** from their real inbox to their `@rfq` address — this is the retention hook: once RFQs flow in automatically, the product is in their workflow.
3. **Invite a colleague** (estimator/sales).
Optional 4th for the Vendor RFQ Portal beta: upload your vendor list (CSV) — offered later, not in session 1.

**Stage 5 · The human, as a feature.** After the first quote: *"Euer Einrichtungs-Ingenieur prüft eure Sätze kostenlos — Termin wählen."* Calendar embed; the rep arrives having seen the org's scrape results, calibration state, and first quotes (Perspective-AI pattern: conversational intake context pushed to CRM). Framed as expert rate review, not sales call. Also triggered proactively if signals stall (no RFQ uploaded in 48h, calibration abandoned, absurd-price guardrail fired).

### The setup assistant (the "Wingman" of onboarding)

A persistent conversational panel (German/English) through all stages — text-first, **voice opt-in** (ElevenLabs/Vapi-class, screen-aware), per the Cor evidence. It can *execute*, not just explain: "Setz meinen Maschinenstundensatz für Laser auf 95 €" → done, with an undo. It answers off-script questions (38% of users start with their own question), deep-links into Configure, and survives onboarding as the product's general assistant. Non-linear by design: every stage skippable, resumable, re-enterable from a "Setup" hub.

### Trial & packaging recommendation

**Free tier: 5 quotes/month forever** (Spanflug-validated in DACH — removes the credit-card barrier and the "trial expired before we had a real RFQ" failure) + **14-day full trial** of everything on signup. No card. Human rate-review included in trial (it's the sales touch).

### What NOT to build

Long welcome quiz (one question + scrape instead) · mandatory product tour (15% median completion) · demo-data-first experience (their data or nothing) · mandatory voice · 10-item checklist · forms for things the agent can extract · gating the first quote behind "complete your setup."

### Metrics & instrumentation (build from day one)

| Step | Target |
|---|---|
| Signup → shop profile confirmed | < 3 min, ≥80% of signups |
| Machine park selected (≥1 machine) | ≥85%; scrape pre-selection accuracy (accept rate) ≥60% |
| Setup Interview started / completed (session 1) | ≥70% started, ≥50% completed |
| Interview: % of pricing-critical values with `interview` provenance | ≥80% among completers |
| Signup → first RFQ uploaded/forwarded | < 15 min, ≥60% |
| Signup → first priced quote (session 1) | < 20 min, ≥50% |
| Activation: own-RFQ quote **sent** ≤ 7 days | ≥35% (top-quartile ambition) |
| Calibration completed ≤ 14 days | ≥40% |
| Guardrail: absurd-price events in week 1 | ~0 (alert on every fire) |

Funnel events on every stage transition; scrape-accuracy feedback (card accept/edit rates) feeds the same correction-logging pattern as extraction.

### Build implications (for the spec)

New components: **OnboardingAgent** (orchestrates scrape → profile → machine picker → interview → execution, on the existing Claude pipeline), **Machine Catalog** (curated DACH machine database: brand/model/class → capabilities → implied operations/processes/interrogation profile/default rate; seed-data workstream alongside the rate library; admin-extensible; "describe it" fallback classifies uncataloged machines), **machine→operations inference map** (per machine class: generated ops + supporting ops per process family), **Setup Interview engine** (agenda/topic state machine + question templates with pre-seeded suggestions + tool-calls that write Configure objects with provenance + live config-preview panel + transcript persistence; text now, voice adapter later), **website scraper** service (robots-respecting, Impressum/VAT-ID aware), **ShopProfile** inference schema, **DACH default rate library** (seed-data workstream — needs real market research per machine class; serves as pre-fill + fallback + sanity bounds), **rate calibration solver** (bounded least-squares cross-check against provided prices + outlier guards), **provenance field** (`interview|scraped|default|calibrated`) on all rate/pricing config, **confidence/guardrail layer** on pricing display, funnel instrumentation. Reuses: extraction pipeline, email ingest, process templates, suggestion-card pattern, Clerk, i18n.

**Generalize the interview pattern:** the same engine later runs scoped mini-interviews for any "personal data" moment — adding a machine ("new Trumpf? two questions and it's costed"), enabling the Vendor RFQ Portal (vendor list), onboarding a new estimator, or the post-pilot ERP setup. One pattern, built once.

Milestone fit: instrumentation + suggestion-card pattern land early (M1–M3); the full onboarding flow is **M6 scope before pilot** (pilot shops should experience it); the voice adapter is post-pilot.

---

## Sources (key)

[ProductLed: AI Onboarding maturity model](https://productled.com/blog/ai-onboarding) · [HubSpot signup architecture](https://product.hubspot.com/blog/signup-architecture) · [Lenny's activation benchmarks](https://www.lennysnewsletter.com/p/what-is-a-good-activation-rate) · [Userpilot checklist benchmarks](https://userpilot.com/blog/onboarding-checklist-completion-rate-benchmarks/) · [Cor/Obi voice-onboarding data](https://www.growthmates.news/p/voice-ai-for-onboarding-what-the) · [Paperless Parts implementation (8–12 wks)](https://www.paperlessparts.com/implementation-and-onboarding/) · [DigiFabster AI price calibration](https://digifabster.com/product/train-your-quote-engine-like-youd-train-a-new-estimator/) · [Spanflug Make zero-config](https://www.mikutec.ch/software-kostenkalkulation-spanflug-fuer-fertiger/) · [Tempus ToolBox trial](https://tempustools.com/pricing/) · [Stella Source wizard (The Fabricator)](https://www.thefabricator.com/thefabricator/article/cadcamsoftware/metal-fabrication-quoting-startup-lowers-the-barrier-to-entry) · [247TailorSteel Sophia](https://247tailorsteel.com/en/sophia) · [Practical Machinist on PP pricing](https://www.practicalmachinist.com/forum/threads/what-is-the-deal-with-paperless-parts.431259/) · [DigiFabster accuracy churn review](https://www.softwareadvice.com/manufacturing/digifabsterquickquote-profile/) · [Hybrid onboarding satisfaction](https://www.saashero.net/customer-retention/b2b-saas-conversion-benchmarks-journey/)
