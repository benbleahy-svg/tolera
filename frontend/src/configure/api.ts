/**
 * Configure → Custom Tables API (M1.9, spec #kalk-tables) — the org tables
 * behind Kalk `table_var`/`table_lookup`. Column types are
 * boolean | numeric | string; a null cell is an empty cell.
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiFetch, apiUpload, type TokenGetter } from '../api/client';

export type ColumnType = 'boolean' | 'numeric' | 'string';

export interface ColumnSpec {
  name: string;
  type: ColumnType;
}

export type CellValue = boolean | number | string | null;
export type TableRowData = Record<string, CellValue>;

export interface CustomTableOut {
  id: string;
  name: string;
  columns: ColumnSpec[];
  row_count: number;
}

export interface CustomTableDetail extends CustomTableOut {
  rows: ({ row_number: number } & TableRowData)[];
}

export type DefCalcType = 'markup' | 'margin' | 'target_margin';
export type DefCategory =
  | 'general'
  | 'material'
  | 'inside'
  | 'outside'
  | 'purchased_component';

export interface PricingItemDefOut {
  id: string;
  name: string;
  calc_type: DefCalcType;
  category: DefCategory;
  is_custom: boolean;
  custom_category_name: string | null;
  color: string | null;
  formula: string | null;
  default_pct: string | null;
  position: number;
}

export interface PricingItemDefBody {
  name: string;
  calc_type: DefCalcType;
  category?: DefCategory;
  is_custom?: boolean;
  custom_category_name?: string | null;
  color?: string | null;
  formula?: string | null;
  default_pct?: string | null;
  position?: number;
}

export interface DiscountDefOut {
  id: string;
  name: string;
  formula: string | null;
  default_pct: string | null;
  position: number;
}

export interface ConfigCompleteness {
  unrated_operation_defs: number;
  unrated_materials: number;
}

/** A review rule row — the canonical AST fields + internal id/is_active
 * (M3.6, spec #rules-schema). The AST is opaque JSON here; the Create Rule
 * editor arrives with M3.8. */
export interface RuleOut {
  id: string;
  uuid: string;
  name: string;
  description: string;
  logical_operator: 'AND' | 'OR';
  signals: { logical_operator: string; groups: unknown[] }[];
  resolutions: { type: string; parameters: unknown[]; custom_label: string | null }[];
  default_assignee_id: string | null;
  is_active: boolean;
}

export interface OperationDefUpdateBody {
  name?: string;
  run_rate?: string | null;
  labour_rate?: string | null;
  setup_cost?: string | null;
  setup_time_mins?: string | null;
  surcharge_pct?: string;
  cost_formula?: string | null;
}

export interface ConfigureApi {
  listOperationDefs: (q: string) => Promise<import('../estimating/types').OperationDefOut[]>;
  updateOperationDef: (defId: string, body: OperationDefUpdateBody) => Promise<unknown>;
  kalkCheck: (formula: string) => Promise<import('../estimating/types').KalkCheckResult>;
  getConfigCompleteness: () => Promise<ConfigCompleteness>;
  applyRateToAll: (runRate: string) => Promise<{ updated: number }>;
  listTables: () => Promise<CustomTableOut[]>;
  getTable: (tableId: string) => Promise<CustomTableDetail>;
  createTable: (name: string, columns: ColumnSpec[]) => Promise<CustomTableOut>;
  renameTable: (tableId: string, name: string) => Promise<CustomTableOut>;
  deleteTable: (tableId: string) => Promise<void>;
  replaceRows: (tableId: string, rows: TableRowData[]) => Promise<CustomTableDetail>;
  importCsv: (tableId: string, file: File) => Promise<CustomTableOut>;
  listPricingItemDefs: () => Promise<PricingItemDefOut[]>;
  createPricingItemDef: (body: PricingItemDefBody) => Promise<PricingItemDefOut>;
  updatePricingItemDef: (
    defId: string,
    body: Partial<PricingItemDefBody>,
  ) => Promise<PricingItemDefOut>;
  deletePricingItemDef: (defId: string) => Promise<void>;
  listDiscountDefs: () => Promise<DiscountDefOut[]>;
  createDiscountDef: (body: {
    name: string;
    default_pct?: string | null;
    formula?: string | null;
  }) => Promise<DiscountDefOut>;
  deleteDiscountDef: (defId: string) => Promise<void>;
  listRules: () => Promise<RuleOut[]>;
  exportRules: () => Promise<{ rules_json: string; count: number }>;
  importRules: (rulesJson: string) => Promise<{ created: number; updated: number }>;
}

export function useConfigureApi(): ConfigureApi {
  const { getToken } = useAuth();
  return useMemo<ConfigureApi>(() => {
    const token: TokenGetter = () => getToken();
    return {
      listOperationDefs: (q) => apiFetch(`/api/operation-defs?q=${encodeURIComponent(q)}`, token),
      updateOperationDef: (defId, body) =>
        apiFetch(`/api/operation-defs/${defId}`, token, { method: 'PATCH', body }),
      kalkCheck: (formula) =>
        apiFetch('/api/kalk/check', token, { method: 'POST', body: { formula } }),
      getConfigCompleteness: () => apiFetch('/api/config-completeness', token),
      applyRateToAll: (runRate) =>
        apiFetch('/api/operation-defs/apply-rate', token, {
          method: 'POST',
          body: { run_rate: runRate },
        }),
      listTables: () => apiFetch('/api/custom-tables', token),
      getTable: (tableId) => apiFetch(`/api/custom-tables/${tableId}`, token),
      createTable: (name, columns) =>
        apiFetch('/api/custom-tables', token, { method: 'POST', body: { name, columns } }),
      renameTable: (tableId, name) =>
        apiFetch(`/api/custom-tables/${tableId}`, token, { method: 'PATCH', body: { name } }),
      deleteTable: (tableId) =>
        apiFetch(`/api/custom-tables/${tableId}`, token, { method: 'DELETE' }),
      replaceRows: (tableId, rows) =>
        apiFetch(`/api/custom-tables/${tableId}/rows`, token, { method: 'PUT', body: { rows } }),
      importCsv: (tableId, file) => {
        const form = new FormData();
        form.append('file', file);
        return apiUpload(`/api/custom-tables/${tableId}/import`, token, form);
      },
      listPricingItemDefs: () => apiFetch('/api/pricing-item-defs', token),
      createPricingItemDef: (body) =>
        apiFetch('/api/pricing-item-defs', token, { method: 'POST', body }),
      updatePricingItemDef: (defId, body) =>
        apiFetch(`/api/pricing-item-defs/${defId}`, token, { method: 'PATCH', body }),
      deletePricingItemDef: (defId) =>
        apiFetch(`/api/pricing-item-defs/${defId}`, token, { method: 'DELETE' }),
      listDiscountDefs: () => apiFetch('/api/discount-defs', token),
      createDiscountDef: (body) =>
        apiFetch('/api/discount-defs', token, { method: 'POST', body }),
      deleteDiscountDef: (defId) =>
        apiFetch(`/api/discount-defs/${defId}`, token, { method: 'DELETE' }),
      listRules: () => apiFetch('/api/rules', token),
      exportRules: () => apiFetch('/api/rules/export', token),
      importRules: (rulesJson) =>
        apiFetch('/api/rules/import', token, { method: 'POST', body: { rules_json: rulesJson } }),
    };
  }, [getToken]);
}
