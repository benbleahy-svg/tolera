-- =====================================================================
-- Tolera (Bid Factory) — Canonical Database Schema (PostgreSQL)
-- Derived from DOMAIN-MODEL.md. First-cut DDL for Claude Code to refine.
-- Conventions:
--   * every tenant-scoped table carries org_id (FK organization) — RLS by org_id.
--   * ids = uuid (gen_random_uuid()); created_at/updated_at timestamptz; soft-delete via deleted_at.
--   * money = numeric(14,4) + a currency char(3) on the owning aggregate (EUR/CHF — DACH).
--   * lengths/areas/volumes stored METRIC (mm, mm2, mm3) — no imperial path (DACH-DELTA-LAYER §1).
--   * per-quantity-break values live in *_quantity / *_cell tables (NOT JSONB) for analytics.
--   * calculated vs override: store both calc_* and manual_* columns; effective = COALESCE(manual_*, calc_*).
-- See DOMAIN-MODEL.md (entities), PRICING-ENGINE-SPEC.md (roll-up), DACH-DELTA-LAYER.md (tax/material).
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------- enums ----------
CREATE TYPE org_country         AS ENUM ('DE','AT','CH');
CREATE TYPE membership_role     AS ENUM ('admin','estimator','salesperson','viewer');
CREATE TYPE account_type        AS ENUM ('customer','vendor');
CREATE TYPE vat_profile         AS ENUM ('domestic','eu_b2b_reverse_charge','non_eu','kleinunternehmer','tax_exempt');
CREATE TYPE obtain_method       AS ENUM ('MANUFACTURED','PURCHASED');
CREATE TYPE quote_status        AS ENUM ('draft','sent','won','lost','expired');
CREATE TYPE qi_workflow_status  AS ENUM ('not_started','in_progress','on_hold','completed','no_quote');
CREATE TYPE order_status        AS ENUM ('confirmed','in_production','shipped','delivered','cancelled');
CREATE TYPE op_category         AS ENUM ('operation','material');
CREATE TYPE calc_type           AS ENUM ('markup','margin');
CREATE TYPE cost_category       AS ENUM ('general','material','inside','outside','purchased_component');
CREATE TYPE process_family      AS ENUM ('SHEET_METAL','MILLING','LATHE','TUBE_LASER','WIRE_EDM','CAST_URETHANE','ADDITIVE','ASSEMBLY','GENERIC');
CREATE TYPE finding_category    AS ENUM ('quote_setup','requirements','features','dimensions','regions');
CREATE TYPE finding_status      AS ENUM ('suggested','accepted','rejected','edited');
CREATE TYPE task_status         AS ENUM ('open','overdue','resolved');
CREATE TYPE export_regime       AS ENUM ('none','eu_dual_use','itar');   -- DACH: default eu_dual_use, not ITAR

-- ---------- identity & org ----------
CREATE TABLE organization (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  slug text UNIQUE NOT NULL,                  -- e.g. 'fechner' → {slug}@rfq.tolera.eu
  country org_country NOT NULL DEFAULT 'DE',
  currency char(3) NOT NULL DEFAULT 'EUR',
  locale text NOT NULL DEFAULT 'de-DE',
  default_tolerance_class text DEFAULT 'ISO 2768-m',   -- DACH-DELTA §4
  export_regime export_regime NOT NULL DEFAULT 'eu_dual_use',
  brand jsonb DEFAULT '{}'::jsonb,            -- white-label config
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app_user (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email citext UNIQUE NOT NULL,
  first_name text, last_name text, job_title text,
  auth_provider_id text,                      -- Clerk
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_org_membership (            -- E4-a: one user ↔ many orgs
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_user(id),
  org_id  uuid NOT NULL REFERENCES organization(id),
  role membership_role NOT NULL DEFAULT 'estimator',
  is_active boolean NOT NULL DEFAULT true,
  date_joined timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, org_id)
);

CREATE TABLE send_from_facility (             -- the shop's own facilities (≠ account_facility)
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  name text NOT NULL, address jsonb
);

-- ---------- CRM ----------
CREATE TABLE account (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  name text NOT NULL,
  type account_type NOT NULL DEFAULT 'customer',
  vat_id text,                                -- USt-IdNr (VIES-validated)
  vat_id_validated_at timestamptz,
  vat_profile vat_profile NOT NULL DEFAULT 'domestic',
  tax_exempt boolean NOT NULL DEFAULT false,
  payment_terms text, credit_line numeric(14,2),
  purchase_orders_enabled boolean NOT NULL DEFAULT true,
  erp_code text, datev_debtor_no text,
  salesperson_id uuid REFERENCES app_user(id),
  phone text, phone_ext text, website text, email citext, notes text,
  billing_address jsonb, shipping_address jsonb,   -- shipping auto-filled at checkout
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE contact (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  account_id uuid REFERENCES account(id),     -- a contact belongs to exactly one account
  email citext NOT NULL,
  first_name text, last_name text, phone text, phone_ext text, notes text,
  salesperson_id uuid REFERENCES app_user(id),
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,
  UNIQUE (org_id, email)                       -- unique email per org
);

CREATE TABLE account_facility (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  account_id uuid NOT NULL REFERENCES account(id),
  name text NOT NULL, attention text, address jsonb,
  deleted_at timestamptz
);

-- ---------- intake (RFQ) ----------
CREATE TABLE request_for_quote (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  rfq_number text,
  business_name text, first_name text, last_name text, email citext, phone text,
  description text, referrer text, marketing_source text,
  requested_delivery_date date,
  export_controlled boolean DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  processed_on timestamptz,
  quote_id uuid                                 -- set once converted (FK added after quote)
);

CREATE TABLE request_for_quote_view (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  rfq_id uuid REFERENCES request_for_quote(id),
  has_started_contact bool, has_finished_contact bool,
  has_started_part_details bool, has_finished_part_details bool,
  has_submitted_file bool, submitted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------- materials (3-level hierarchy; DACH DIN/EN) ----------
CREATE TABLE material_class  ( id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL REFERENCES organization(id), name text NOT NULL );
CREATE TABLE material_family ( id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL REFERENCES organization(id), class_id uuid NOT NULL REFERENCES material_class(id), name text NOT NULL );
CREATE TABLE material (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  family_id uuid NOT NULL REFERENCES material_family(id),
  werkstoffnummer text,                        -- DIN EN 10027, e.g. '1.4301'  (DACH-DELTA §4)
  en_name text,                                -- 'X5CrNi18-10'
  aisi_alias text,                             -- '304' (reference)
  display_name text NOT NULL,
  density numeric(10,4),                       -- g/cm3
  cost_per_volume numeric(14,6), cost_per_area numeric(14,6),
  added_lead_time_days int DEFAULT 0
);

-- ---------- process / operation defs ----------
CREATE TABLE process (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  name text NOT NULL, external_name text,
  family process_family NOT NULL DEFAULT 'GENERIC',
  is_default_purchased_component_process boolean DEFAULT false,
  available_in_smart_rfq boolean DEFAULT false,
  default_lead_time_days int DEFAULT 0,
  deleted_at timestamptz
);

CREATE TABLE operation_def (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  name text NOT NULL,
  category op_category NOT NULL DEFAULT 'operation',
  is_outside_service boolean DEFAULT false,
  is_finish boolean DEFAULT false,
  calc_mode text,                              -- calculation mode
  cost_formula text,                           -- Kalk (operation-cost context)
  surcharge_pct numeric(6,3) DEFAULT 0,        -- spec: optional op surcharge
  runtime_display_units text DEFAULT 'hr', setup_time_display_units text DEFAULT 'hr',
  erp_code text, deleted_at timestamptz
);

-- process router membership (which op defs a process generates, with flags)
CREATE TABLE process_operation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  process_id uuid NOT NULL REFERENCES process(id),
  operation_def_id uuid NOT NULL REFERENCES operation_def(id),
  position int NOT NULL,
  per_setup boolean DEFAULT false,
  is_assembly boolean DEFAULT false,
  root_component_only boolean DEFAULT false
);

CREATE TABLE custom_table (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  name text NOT NULL,
  columns jsonb NOT NULL                       -- [{name,type}], alphanumeric names
);
CREATE TABLE custom_table_row (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  table_id uuid NOT NULL REFERENCES custom_table(id),
  row_number int NOT NULL,
  data jsonb NOT NULL
);

CREATE TABLE custom_interrogation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  name text NOT NULL,
  family process_family NOT NULL,
  inputs jsonb NOT NULL,                       -- DFM-WARNINGS thresholds/toggles
  material_class_id uuid REFERENCES material_class(id),
  material_family_id uuid REFERENCES material_family(id),
  material_id uuid REFERENCES material(id)
);

-- ---------- parts / geometry / nodes (4-layer core) ----------
CREATE TABLE part (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  part_number text, revision text, description text,
  is_assembly boolean NOT NULL DEFAULT false,
  obtain_method obtain_method NOT NULL DEFAULT 'MANUFACTURED',
  primary_file_id uuid,                        -- FK part_file (added after)
  custom_attributes jsonb DEFAULT '{}'::jsonb,
  geom_hash text,                              -- INTERROGATION-ENGINE §1 signature (historical match)
  export_controlled boolean DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);
CREATE INDEX ON part (org_id, geom_hash);

CREATE TABLE part_file (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  part_id uuid NOT NULL REFERENCES part(id),
  storage_key text NOT NULL, filename text, file_type text,    -- step|print|vector|...
  role text NOT NULL DEFAULT 'supporting',     -- 'primary' | 'supporting'
  is_redacted boolean DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE part ADD CONSTRAINT fk_part_primary_file FOREIGN KEY (primary_file_id) REFERENCES part_file(id);

CREATE TABLE part_geometry (                   -- INTERROGATION output cache (metric)
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  part_id uuid NOT NULL REFERENCES part(id),
  size_x numeric, size_y numeric, size_z numeric,
  max_dim numeric, med_dim numeric, min_dim numeric,
  area numeric, volume numeric, weight numeric,
  raw jsonb,                                   -- full AnalysisResult by family
  overrides jsonb                              -- user dimension overrides (raw vs override vs resolved)
);

CREATE TABLE node (                            -- occurrence of a part in a tree
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  part_id uuid NOT NULL REFERENCES part(id),
  parent_node_id uuid REFERENCES node(id),     -- null = root node (qty 1)
  qty_relative_to_parent int NOT NULL DEFAULT 1,
  root_part_id uuid                            -- denormalized tree root for fast scoping
);
CREATE INDEX ON node (parent_node_id);

-- ---------- quoting ----------
CREATE TABLE quote (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  number text NOT NULL, revision int DEFAULT 0,
  status quote_status NOT NULL DEFAULT 'draft',
  account_id uuid REFERENCES account(id),
  contact_id uuid REFERENCES contact(id),      -- required to send
  estimator_id uuid REFERENCES app_user(id),
  salesperson_id uuid REFERENCES app_user(id),
  send_from_facility_id uuid REFERENCES send_from_facility(id),
  currency char(3) NOT NULL DEFAULT 'EUR',
  rfq_number text, rfq_received_date timestamptz,
  due_date timestamptz, started_at timestamptz, sent_at timestamptz, expired_at timestamptz,
  estimator_assigned_at timestamptz, salesperson_assigned_at timestamptz,
  digital_last_viewed_at timestamptz,
  lead_time_display_units text DEFAULT 'business_days',
  mark_sent_or_finalized text,                 -- 'finalized' | 'mark_sent'
  private_notes text, email_thread_id text,
  config_frozen_at timestamptz,                -- E4-d freeze marker
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON quote (org_id, status);
ALTER TABLE request_for_quote ADD CONSTRAINT fk_rfq_quote FOREIGN KEY (quote_id) REFERENCES quote(id);

-- A Component is a Part with pricing. Root component == quote item.
CREATE TABLE component (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  part_id uuid NOT NULL REFERENCES part(id),
  process_id uuid REFERENCES process(id),
  material_id uuid REFERENCES material(id),
  obtain_method obtain_method NOT NULL DEFAULT 'MANUFACTURED',
  is_root_component boolean NOT NULL DEFAULT false,
  is_assembly boolean NOT NULL DEFAULT false,
  purchased_component_id uuid                   -- FK below
);

CREATE TABLE quote_item (                       -- ties root component to a quote
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  quote_id uuid NOT NULL REFERENCES quote(id),
  root_component_id uuid NOT NULL REFERENCES component(id),
  position int NOT NULL,
  workflow_status qi_workflow_status NOT NULL DEFAULT 'not_started',
  was_won boolean DEFAULT false,
  export_controlled boolean DEFAULT false,
  expired_at timestamptz
);
CREATE INDEX ON quote_item (quote_id, position);

CREATE TABLE component_quantity (               -- per quantity break — richest entity
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  component_id uuid NOT NULL REFERENCES component(id),
  quantity int NOT NULL,                        -- customer requested
  make_quantity int, deliver_quantity int,      -- computed from tree position
  unit_cost numeric(14,4),
  calc_unit_price numeric(14,4), manual_unit_price numeric(14,4),  -- override pattern
  unit_price numeric(14,4),                      -- incl. discounts (buyer-facing)
  total_price numeric(14,4),
  material_cost numeric(14,4), inside_cost numeric(14,4), outside_cost numeric(14,4),
  purchased_component_cost numeric(14,4), child_override_cost numeric(14,4),
  total_discount numeric(14,4), total_discount_pct numeric(7,4),
  total_profit numeric(14,4), profit_margin_pct numeric(7,4),
  lead_time_days int,
  is_most_likely_won boolean DEFAULT false,
  UNIQUE (component_id, quantity)
);

CREATE TABLE purchased_component (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  oem_part_number text, internal_part_number text,
  piece_price numeric(14,4), description text,
  insertion_time numeric(10,2),
  custom_columns jsonb DEFAULT '{}'::jsonb       -- org-defined columns
);
ALTER TABLE component ADD CONSTRAINT fk_comp_pc FOREIGN KEY (purchased_component_id) REFERENCES purchased_component(id);

-- operations on a component (instances of operation_def)
CREATE TABLE operation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  component_id uuid NOT NULL REFERENCES component(id),
  operation_def_id uuid REFERENCES operation_def(id),   -- null = manual op
  dynamic_name text, position int,
  category op_category, is_outside_service boolean, is_finish boolean,
  is_from_factory boolean DEFAULT true,          -- false = manually added
  variables jsonb DEFAULT '{}'::jsonb            -- declared vars + overrides
);

CREATE TABLE quote_cell (                         -- operation cost per quantity break
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  operation_id uuid NOT NULL REFERENCES operation(id),
  quantity int NOT NULL,
  calc_cost numeric(14,4), manual_cost numeric(14,4),
  runtime numeric(12,4), setup_time numeric(12,4), days int,
  UNIQUE (operation_id, quantity)
);

-- pricing items / discounts / add-ons / custom cost categories (each + per-quantity cell)
CREATE TABLE pricing_item (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  component_id uuid NOT NULL REFERENCES component(id),  -- root component
  name text, calc_type calc_type NOT NULL DEFAULT 'markup',
  category cost_category NOT NULL DEFAULT 'general',
  is_custom boolean DEFAULT false, formula text,        -- Kalk (pricing context)
  is_from_factory boolean DEFAULT true
);
CREATE TABLE pricing_item_cell (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  pricing_item_id uuid NOT NULL REFERENCES pricing_item(id),
  quantity int NOT NULL,
  calc_pct numeric(9,4), manual_pct numeric(9,4),
  calc_profit numeric(14,4), manual_profit numeric(14,4),
  UNIQUE (pricing_item_id, quantity)
);

CREATE TABLE discount (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  component_id uuid NOT NULL REFERENCES component(id),
  name text, formula text, is_from_factory boolean DEFAULT true
);
CREATE TABLE discount_cell (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  discount_id uuid NOT NULL REFERENCES discount(id),
  quantity int NOT NULL,
  calc_pct numeric(9,4), manual_pct numeric(9,4),
  UNIQUE (discount_id, quantity)
);

CREATE TABLE add_on (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  component_id uuid NOT NULL REFERENCES component(id),
  name text, is_required boolean DEFAULT false, formula text,
  is_from_factory boolean DEFAULT true
);
CREATE TABLE add_on_cell (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  add_on_id uuid NOT NULL REFERENCES add_on(id),
  quantity int NOT NULL,
  calc_price numeric(14,4), manual_price numeric(14,4),
  UNIQUE (add_on_id, quantity)
);

CREATE TABLE expedite_option (                    -- dynamic lead times (E4-c)
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  component_id uuid NOT NULL REFERENCES component(id),
  days_faster int NOT NULL, markup_pct numeric(7,3) NOT NULL
);

CREATE TABLE nest (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  quote_id uuid REFERENCES quote(id),
  label text, kind text,                          -- sheet|linear
  config jsonb, result jsonb
);

-- ---------- orders ----------
CREATE TABLE "order" (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  number text NOT NULL, quote_id uuid REFERENCES quote(id),
  status order_status NOT NULL DEFAULT 'confirmed',
  total_price numeric(14,4), total_expedite_fees numeric(14,4),
  currency char(3) NOT NULL DEFAULT 'EUR',
  po_number text, payment_method text,            -- po|sepa|card|qr_bill
  created_at timestamptz NOT NULL DEFAULT now(), last_status_change_at timestamptz
);
CREATE TABLE order_item (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id uuid NOT NULL REFERENCES "order"(id),
  quote_item_id uuid REFERENCES quote_item(id),
  quantity int, unit_price numeric(14,4), total_price numeric(14,4),
  shipping_price numeric(14,4), expedite_fee numeric(14,4),
  ships_on date
);
CREATE TABLE order_adjustment (                    -- post-order changes (E? / OrderHistory)
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id uuid NOT NULL REFERENCES "order"(id),
  kind text, detail jsonb, created_by uuid REFERENCES app_user(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------- workflow / rules / review / tasks / notifications ----------
CREATE TABLE workflow_step_def (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  name text NOT NULL, position int NOT NULL
);
CREATE TABLE quote_item_workflow_step (            -- per-item status per custom step
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  quote_item_id uuid NOT NULL REFERENCES quote_item(id),
  step_def_id uuid NOT NULL REFERENCES workflow_step_def(id),
  status qi_workflow_status NOT NULL DEFAULT 'not_started',
  UNIQUE (quote_item_id, step_def_id)
);

CREATE TABLE rule (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  name text NOT NULL, signals jsonb, filters jsonb, resolution_options jsonb,
  is_active boolean DEFAULT true
);
CREATE TABLE review_item (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  quote_id uuid REFERENCES quote(id), quote_item_id uuid REFERENCES quote_item(id),
  rule_id uuid REFERENCES rule(id),
  status text DEFAULT 'open', detail jsonb, created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE task (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  part_id uuid REFERENCES part(id), quote_id uuid REFERENCES quote(id),
  assignee_id uuid REFERENCES app_user(id), created_by uuid REFERENCES app_user(id),
  message text, due_date date, status task_status NOT NULL DEFAULT 'open',
  annotation_id uuid, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE notification (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_user(id),
  org_id uuid NOT NULL REFERENCES organization(id),   -- source org (cross-org per E4-a)
  kind text, payload jsonb, read_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------- collaboration / sourcing ----------
CREATE TABLE channel (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  quote_id uuid REFERENCES quote(id), part_id uuid REFERENCES part(id),
  scope text NOT NULL DEFAULT 'team'                 -- 'team' | 'external'
);
CREATE TABLE message (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  channel_id uuid NOT NULL REFERENCES channel(id),
  author_id uuid REFERENCES app_user(id), body text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE annotation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  part_id uuid REFERENCES part(id), kind text, geometry_ref jsonb, note text
);
CREATE TABLE external_share (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  quote_id uuid REFERENCES quote(id), token text UNIQUE NOT NULL,
  expires_at timestamptz, revoked_at timestamptz
);

-- ---------- AI / Lens extractions ----------
CREATE TABLE extraction_finding (                    -- AI-LENS-ENGINE §8
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  component_id uuid REFERENCES component(id),
  source_file_id uuid REFERENCES part_file(id),
  page int, category finding_category NOT NULL, type text,
  raw_text text, value text, normalized_value text, units text,
  tolerance jsonb,                                   -- {kind,upper,lower}
  role text,                                         -- basic|critical_to_quality|reference
  gdt jsonb,                                         -- ISO GPS {symbol,datum_refs,material_condition}
  bbox jsonb, confidence numeric(5,4),
  status finding_status NOT NULL DEFAULT 'suggested',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE extraction_correction (                 -- training feedback loop
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  finding_id uuid REFERENCES extraction_finding(id),
  predicted text, corrected text, corrected_by uuid REFERENCES app_user(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------- e-invoicing archive (GoBD, DACH-DELTA §3) ----------
CREATE TABLE einvoice (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organization(id),
  order_id uuid REFERENCES "order"(id),
  invoice_number text NOT NULL,                      -- sequential, immutable (§14 UStG)
  format text,                                       -- zugferd|xrechnung|peppol
  xml bytea, pdf bytea, issued_at timestamptz,
  archived_until date                                -- GoBD ~10y retention
);

-- =====================================================================
-- Notes:
--  * Tax (MwSt/USt) is computed at quote/order level by a Tax/Region service, NOT stored on cells
--    (PRICING-ENGINE-SPEC §1; DACH-DELTA §3). Add quote_tax / order_tax lines as that service is built.
--  * Enforce row-level security by org_id on every tenant table.
--  * "effective" cell value = COALESCE(manual_*, calc_*); never overwrite calc_* with overrides.
--  * Status enums seed the lifecycle in USER-STORIES-AND-WORKFLOWS.md.
-- =====================================================================
