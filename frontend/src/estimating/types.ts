/**
 * Wire types for the part-estimating Materials & Operations surface (M1.7):
 * the component costing read (`/api/components/:id/costing`), the material
 * picker (`/api/materials*`), processes and the operation library. Cost values
 * arrive as JSON strings (backend `numeric(14,4)`) — never parse into floats
 * for arithmetic; the UI only formats them.
 */

export type OpCategory = 'operation' | 'material';
export type CalculationMode = 'machine_plus_operator' | 'labour_only' | 'outside_process';
export type SetupBasis = 'flat' | 'time';

export interface QuoteCellOut {
  quantity: number;
  calc_cost: string | null;
  manual_cost: string | null;
  effective_cost: string | null;
}

export interface OperationOut {
  id: string;
  operation_def_id: string | null;
  name: string;
  category: OpCategory;
  position: number;
  calculation_mode: CalculationMode;
  run_rate: string | null;
  labour_rate: string | null;
  setup_basis: SetupBasis;
  setup_cost: string | null;
  calc_setup_mins: string | null;
  manual_setup_mins: string | null;
  calc_runtime_mins: string | null;
  manual_runtime_mins: string | null;
  calc_attend_mins: string | null;
  manual_attend_mins: string | null;
  surcharge_pct: string;
  yield_factor: string;
  is_outside_service: boolean;
  is_finish: boolean;
  is_from_factory: boolean;
  notes: string | null;
  cost_formula: string | null;
  variable_overrides: Record<string, VariableOverrideValue>;
  /** M4.13 provenance: 'imported' rows carry the source-quote stamp. */
  source: 'manual' | 'imported' | 'ai_drafted';
  source_quote_id: string | null;
  missing_rate: boolean;
  cells: QuoteCellOut[];
}

/** A Kalk variable override: plain value, or `{ "<qty>": value }` per break. */
export type OverrideScalar = boolean | number | string;
export type VariableOverrideValue = OverrideScalar | Record<string, OverrideScalar>;

export interface KalkError {
  code: string;
  message: string;
  line: number | null;
  col: number | null;
}

export interface KalkCheckResult {
  ok: boolean;
  errors: KalkError[];
}

/** One declared variable from an evaluation (drawer variables panel). */
export interface KalkDeclaredVariable {
  name: string;
  kind?: 'var' | 'drop_down' | 'table_var';
  value_type: string;
  default: OverrideScalar | null;
  description: string;
  default_visible: boolean;
  frozen: boolean;
  quantity_specific: boolean;
  value: OverrideScalar | null;
  options?: OverrideScalar[] | { row_number: number; display: string }[];
  table_name?: string;
  display_column_name?: string | null;
}

export interface KalkVariableGroup {
  name: string;
  default_collapsed: boolean;
  members: string[];
}

/** One quantity break's evaluation in the drawer report. */
export interface KalkQtyReport {
  quantity: number;
  output: Record<string, unknown> | null;
  declared_variables: KalkDeclaredVariable[];
  variable_groups: KalkVariableGroup[];
  applied_overrides: string[];
  notes: string | null;
  operation_name: string | null;
  errors: KalkError[];
}

export interface CostBucket {
  quantity: number;
  material_total: string;
  inside_total: string;
  outside_total: string;
  total: string;
  has_unpriced_rows: boolean;
}

export interface ComponentCosting {
  component_id: string;
  material_id: string | null;
  process_id: string | null;
  quantities: number[];
  operations: OperationOut[];
  buckets: CostBucket[];
  has_missing_rates: boolean;
}

export interface MaterialOut {
  id: string;
  family_id: string;
  display_name: string;
  werkstoffnummer: string | null;
  en_name: string | null;
  aisi_alias: string | null;
  density: string | null;
  cost_per_volume: string | null;
  cost_per_area: string | null;
  added_lead_time_days: number;
}

export interface MaterialSearchHit extends MaterialOut {
  class_name: string;
  family_name: string;
  path: string;
}

export interface FamilyNode {
  id: string;
  name: string;
  alias: string | null;
  materials: MaterialOut[];
}

export interface ClassNode {
  id: string;
  name: string;
  families: FamilyNode[];
}

export interface ProcessOut {
  id: string;
  name: string;
  external_name: string | null;
}

export interface OperationDefOut {
  id: string;
  name: string;
  category: OpCategory;
  calculation_mode: CalculationMode;
  run_rate: string | null;
  labour_rate: string | null;
  setup_basis: SetupBasis;
  setup_cost: string | null;
  setup_time_mins: string | null;
  surcharge_pct: string;
  is_outside_service: boolean;
  is_finish: boolean;
  is_pre_installed: boolean;
  sort_order: number;
  cost_formula: string | null;
  /** M4.14 Variables-table eye toggles — overlay over the formula defaults. */
  variable_visibility: Record<string, boolean>;
}

/** M4.14: the def-level Variables-table report (synthetic-context eval).
 * `variable_visibility` is the def's stored eye map — the base for the next
 * full-replace PUT (never a cached defs-list row). */
export interface OpDefKalkReport {
  declared_variables: KalkDeclaredVariable[];
  variable_groups: KalkVariableGroup[];
  errors: KalkError[];
  variable_visibility: Record<string, boolean>;
}

/** The subset of the quote-detail response the estimating page reads (M1.4/M1.6). */
export interface QuoteItemSummary {
  id: string;
  position: number;
  root_component_id: string;
  part_id: string;
  workflow_status: string;
  /** M5.0 #partview — per-line-item priority (higher = more urgent), or null. */
  priority: number | null;
  quantities: { quantity: number; make_quantity: number; deliver_quantity: number }[];
}

export interface QuoteSummary {
  id: string;
  number: string;
  status: string;
  currency: string;
  missing_rates_item_count: number;
  items: QuoteItemSummary[];
}

// ---- Bulk Create Line Items (M3.4 — spec #wingman, DemoB/04) ---- //

/** One suggestion row + its file-distribution preview (GET prefill). */
export interface BulkCreatePrefillRow {
  part_number: string;
  revision: string | null;
  description: string | null;
  quantities: number[];
  requested_date: string | null;
  confidence: number;
  matched_part_id: string | null;
  matched_filenames: string[];
}

export interface BulkCreatePrefill {
  status: 'none' | 'pending' | 'completed' | 'failed';
  found_in: string | null;
  rfq_files: { filename: string; original_rfq: boolean }[];
  rows: BulkCreatePrefillRow[];
}

/** One dialog row at Accept time — the editable columns plus the reviewed
 * file-distribution binding (null = let the server match). */
export interface BulkCreateRowBody {
  part_number: string;
  revision?: string | null;
  description?: string | null;
  quantities: number[];
  matched_part_id?: string | null;
}

export interface OperationCreateBody {
  operation_def_id?: string;
  name?: string;
  category?: OpCategory;
  calculation_mode?: CalculationMode;
  run_rate?: string;
  labour_rate?: string;
  setup_cost?: string;
}

export interface OperationUpdateBody {
  name?: string;
  calculation_mode?: CalculationMode;
  run_rate?: string | null;
  labour_rate?: string | null;
  setup_basis?: SetupBasis;
  setup_cost?: string | null;
  manual_setup_mins?: string | null;
  manual_runtime_mins?: string | null;
  manual_attend_mins?: string | null;
  surcharge_pct?: string;
  yield_factor?: string;
  is_outside_service?: boolean;
  is_finish?: boolean;
  notes?: string | null;
  cost_formula?: string | null;
}

export interface MaterialUpdateBody {
  display_name?: string;
  density?: string | null;
  cost_per_volume?: string | null;
  cost_per_area?: string | null;
  added_lead_time_days?: number;
}

// --------------------------------------------------------------------------- //
// M1.10 — pricing (costing roll-up + pricing items + discounts)
// --------------------------------------------------------------------------- //
export type CalcType = 'markup' | 'margin' | 'target_margin';
export type PricingCategory =
  | 'general'
  | 'material'
  | 'inside'
  | 'outside'
  | 'purchased_component';

export interface CustomCostRow {
  pricing_item_id: string;
  name: string | null;
  color: string | null;
  cost: string | null;
}

export interface CostingRow {
  quantity: number;
  material: string | null;
  inside: string | null;
  outside: string | null;
  purchased_component: string | null;
  child_override: string | null;
  total: string | null;
  unit_cost: string | null;
  custom_rows: CustomCostRow[];
}

export interface PricingItemCellOut {
  quantity: number;
  calc_pct: string | null;
  manual_pct: string | null;
  pct: string | null;
  calc_profit: string | null;
  manual_profit: string | null;
  amount: string | null;
  calc_custom_cost: string | null;
  unreachable: boolean;
}

export interface PricingItemOut {
  id: string;
  source_def_id: string | null;
  name: string;
  calc_type: CalcType;
  category: PricingCategory;
  is_custom: boolean;
  custom_category_name: string | null;
  color: string | null;
  formula: string | null;
  default_pct: string | null;
  position: number;
  is_from_factory: boolean;
  cells: PricingItemCellOut[];
}

export interface DiscountCellOut {
  quantity: number;
  calc_pct: string | null;
  manual_pct: string | null;
  pct: string | null;
}

export interface DiscountOut {
  id: string;
  source_def_id: string | null;
  name: string;
  formula: string | null;
  default_pct: string | null;
  position: number;
  is_from_factory: boolean;
  cells: DiscountCellOut[];
}

export interface PricingTotalsRow {
  quantity: number;
  unit_cost: string | null;
  total_excl_discounts: string | null;
  total_markup: string | null;
  total_markup_pct: string | null;
  calc_unit_price: string | null;
  manual_unit_price: string | null;
  unit_price: string | null;
  total_price: string | null;
  total_discount: string | null;
  total_discount_pct: string | null;
  total_profit: string | null;
  profit_margin_pct: string | null;
  total_required_add_ons: string | null;
  total_with_required_add_ons: string | null;
}

// --- M1.11: add-ons, lead times, expedite, VAT totals (spec #addons/#dach-tax)

export interface AddOnCellOut {
  quantity: number;
  calc_price: string | null;
  manual_price: string | null;
  price: string | null;
}

export interface AddOnOut {
  id: string;
  source_def_id: string | null;
  name: string;
  formula: string | null;
  default_price: string | null;
  default_is_required: boolean;
  calc_is_required: boolean | null;
  manual_is_required: boolean | null;
  is_required: boolean;
  position: number;
  is_from_factory: boolean;
  cells: AddOnCellOut[];
}

export interface AddOnDefOut {
  id: string;
  name: string;
  formula: string | null;
  default_price: string | null;
  default_is_required: boolean;
  position: number;
}

export interface AddOnCreateBody {
  source_def_id?: string | null;
  name?: string | null;
  formula?: string | null;
  default_price?: string | null;
  is_required?: boolean | null;
}

export interface ExpediteRowOut {
  id: string;
  days_faster: number;
  markup_pct: string;
  lead_time_days: number | null;
  unit_price: string | null;
  total_price: string | null;
}

export interface LeadTimeRowOut {
  quantity: number;
  calc_lead_time_days: number | null;
  manual_lead_time_days: number | null;
  lead_time_days: number | null;
  expedites: ExpediteRowOut[];
}

export interface ExpediteTierBody {
  days_faster: number;
  markup_pct: string;
}

export interface QuoteTotalsItem {
  quote_item_id: string;
  component_id: string;
  quantity: number;
  net_minor: number;
  unpriced: boolean;
}

export interface QuoteTotals {
  currency: string;
  country: string;
  vat_label: string;
  vat_rate_pct: string;
  items: QuoteTotalsItem[];
  net_minor: number;
  vat_minor: number;
  gross_minor: number;
  has_unpriced_lines: boolean;
}

export interface PricingSummary {
  component_id: string;
  quantities: number[];
  costing: CostingRow[];
  pricing_items: PricingItemOut[];
  discounts: DiscountOut[];
  add_ons: AddOnOut[];
  lead_times: LeadTimeRowOut[];
  totals: PricingTotalsRow[];
}

/** Ad-hoc pricing-item fields (also the PATCH body). */
export interface PricingItemFields {
  name: string;
  calc_type?: CalcType;
  category?: PricingCategory;
  is_custom?: boolean;
  custom_category_name?: string | null;
  color?: string | null;
  formula?: string | null;
  default_pct?: string | null;
}

/** Create either FROM the Configure library (snapshot-on-attach — the def
 * supplies every field server-side) OR ad-hoc — never a mix. */
export type PricingItemCreateBody = { source_def_id: string } | PricingItemFields;

export type PricingItemUpdateBody = PricingItemFields;

export type DiscountCreateBody =
  | { source_def_id: string }
  | { name: string; default_pct?: string | null };

/** Configure-library defs offered by the on-quote Add flows. */
export interface PricingItemDefLite {
  id: string;
  name: string;
  calc_type: CalcType;
  category: PricingCategory;
  is_custom: boolean;
  custom_category_name: string | null;
  color: string | null;
  formula: string | null;
  default_pct: string | null;
}

export interface DiscountDefLite {
  id: string;
  name: string;
  formula: string | null;
  default_pct: string | null;
}

// --------------------------------------------------------------------------
// M4.3 — multi-component sheet-metal nesting (spec #nesting)
// --------------------------------------------------------------------------
export interface NestingOverviewRow {
  component_id: string;
  part_id: string;
  part_number: string | null;
  part_name: string | null;
  item_id: string;
  position: number;
  material_id: string | null;
  material_name: string | null;
  thickness_mm: number | null;
  flat_x_mm: number | null;
  flat_y_mm: number | null;
  flat_area_mm2: number | null;
  contour_length_mm: number | null;
  quantities: number[];
  make_quantities: number[];
  eligible: boolean;
  nest_id: string | null;
  nest_label: string | null;
}

export interface NestComponentResult {
  component_id: string;
  parts_per_sheet: number;
  used_area_mm2: number;
  cost_share_pct: string;
  allocated_cost: string;
}

export interface NestResultOut {
  net_sheet_used: number;
  charged_sheets: number;
  gross_sheets: number;
  material_cost: string;
  currency: string;
  used_area_mm2: number;
  scrap_area_mm2: number;
  drop_area_mm2: number;
  total_contour_length_mm: number;
  components: NestComponentResult[];
}

export interface NestOut {
  id: string;
  label: string | null;
  kind: string | null;
  set_id: string | null;
  quantity: number | null;
  config: {
    thickness_mm?: number;
    stock?: {
      length_mm: number;
      width_mm: number;
      erp_code: string;
      sheet_cost: string;
      currency: string;
    };
    component_ids?: string[];
  } | null;
  result: NestResultOut | null;
}

export interface NestingOverview {
  sheet_metal: NestingOverviewRow[];
  linear_metal: NestingOverviewRow[];
  nests: NestOut[];
}

export interface NestStockBody {
  quantity: number;
  length_mm: number;
  width_mm: number;
  erp_code: string;
  sheet_cost: string;
}

export interface NestCreateBody {
  component_ids: string[];
  stock: NestStockBody[];
  settings: {
    edge_buffer_mm: number;
    clearance_mm: number;
    kerf_mm: number;
    drop_threshold_pct: number;
    distribution_method: string;
    allow_mixed_thickness: boolean;
  };
  component_settings: { component_id: string; cost_distribution_pct?: string | null }[];
}

// ---- Assembly Components (M4.10 — spec #assembly) ---- //

export interface AssemblyNodeOut {
  node_id: string;
  part_id: string;
  component_id: string | null;
  part_number: string | null;
  revision: string | null;
  description: string | null;
  filename: string | null;
  group: 'subassembly' | 'manufactured' | 'purchased';
  obtain_method: string;
  is_assembly: boolean;
  node_qty: number;
  flat_qty: number;
  position: number;
  process_id: string | null;
  material_id: string | null;
  piece_price: string | null;
  purchased_component_id: string | null;
  brand: string | null;
  self_costs: string[];
  rollup_costs: string[];
  children: AssemblyNodeOut[];
}

export interface AssemblyComponentsOut {
  quantities: number[];
  root_node_id: string | null;
  tree: AssemblyNodeOut[];
  summary: { flat_qty_total: number; totals: string[] };
}

export interface PurchasedComponentOut {
  id: string;
  oem_part_number: string;
  internal_part_number: string | null;
  piece_price: string | null;
  currency: string;
  description: string | null;
  brand: string | null;
  custom_fields: Record<string, unknown>;
  oem_product_id: string | null;
}

export interface PurchaseMatchCard {
  purchased_component: PurchasedComponentOut;
  oem_part_number_match: boolean;
  oem_geometric_match: boolean;
  historical_geometric_matches: number;
}

export interface PurchaseMatchesOut {
  component: {
    id: string;
    part_number: string | null;
    revision: string | null;
    filename: string | null;
    obtain_method: string;
    piece_price: string | null;
    purchased_component_id: string | null;
  };
  smart: PurchaseMatchCard[];
  unlinked_oem: {
    id: string;
    brand: string;
    oem_part_number: string;
    specs: Record<string, unknown>;
  }[];
  all: PurchasedComponentOut[];
}

export interface PurchasedComponentCreateBody {
  oem_part_number: string;
  internal_part_number?: string | null;
  piece_price?: string | null;
  description?: string | null;
  brand?: string | null;
}

// --- M4.12 — Requote Diff Assistant (spec #ai-requote-diff) ---

/** One serialized ExtractionFinding inside the diff payload. */
export interface RequoteFinding {
  type: string;
  category: string;
  role: string | null;
  value: string | null;
  normalized_value: string | null;
  units: string | null;
  tolerance: Record<string, unknown> | null;
  gdt: Record<string, unknown> | null;
}

export interface RequoteFindingChange {
  key: { type: string; role: string | null };
  a: RequoteFinding;
  b: RequoteFinding;
  changes: string[];
}

export interface RequoteGeometryDelta {
  available: boolean;
  significant: boolean;
  volume?: { a: number; b: number; delta_pct: number };
  bbox?: Record<string, { a: number; b: number; delta: number }>;
  features?: Record<string, { a: number; b: number; delta: number }>;
}

export interface RequoteDiffEntry {
  part_id: string;
  match_type: 'exact_file' | 'exact_geometric';
  matched: {
    part_id: string;
    part_number: string | null;
    revision: string | null;
    quote_id: string;
    quote_number: string;
    component_id: string;
  };
  target_component_id: string;
  diff: {
    geometry_delta: RequoteGeometryDelta;
    finding_diff: {
      added: RequoteFinding[];
      removed: RequoteFinding[];
      changed: RequoteFindingChange[];
      material_changes: { kind: string; reason: string; finding: RequoteFinding }[];
    };
  };
  ai: { enabled: boolean; reason: string } | null;
  synthesis: string | null;
  choice: { choice: RequoteChoice; at: string } | null;
  generated_at: string;
  // --- M4.13 — Agentic Quote Assembly (spec #ai-quote-assembly) ---
  /** "Quoted N times" for the assembly banner (0 on pre-M4.13 entries). */
  quote_count?: number;
  /** The persisted import record (audit trail); null until a path is taken. */
  assembly?: AssemblyRecord | null;
  /** Read-time server state: the offer + the server-computed eligibility. */
  assembly_state?: AssemblyState;
}

export interface AssemblyState {
  offered: boolean;
  accept_all_eligible: boolean;
  blockers: string[];
  quote_count: number;
  undo_ttl_seconds: number;
}

export interface AssemblyRecord {
  path: 'accept_all' | 'review';
  at: string;
  user_id: string;
  source_quote_id: string;
  source_quote_number: string | null;
  undone_at: string | null;
  undo_expires_at: string | null;
}

export type RequoteChoice = 'import_router' | 'review' | 'start_fresh';

export interface RequoteDiffResponse {
  entries: RequoteDiffEntry[];
}
