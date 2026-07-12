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
}

/** The subset of the quote-detail response the estimating page reads (M1.4/M1.6). */
export interface QuoteItemSummary {
  id: string;
  position: number;
  root_component_id: string;
  part_id: string;
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

export interface PricingItemCreateBody {
  name: string;
  calc_type: CalcType;
  category?: PricingCategory;
  is_custom?: boolean;
  custom_category_name?: string | null;
  color?: string | null;
  formula?: string | null;
  default_pct?: string | null;
}
