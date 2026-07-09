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
