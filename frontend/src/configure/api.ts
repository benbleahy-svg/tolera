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

export interface ConfigureApi {
  listTables: () => Promise<CustomTableOut[]>;
  getTable: (tableId: string) => Promise<CustomTableDetail>;
  createTable: (name: string, columns: ColumnSpec[]) => Promise<CustomTableOut>;
  renameTable: (tableId: string, name: string) => Promise<CustomTableOut>;
  deleteTable: (tableId: string) => Promise<void>;
  replaceRows: (tableId: string, rows: TableRowData[]) => Promise<CustomTableDetail>;
  importCsv: (tableId: string, file: File) => Promise<CustomTableOut>;
}

export function useConfigureApi(): ConfigureApi {
  const { getToken } = useAuth();
  return useMemo<ConfigureApi>(() => {
    const token: TokenGetter = () => getToken();
    return {
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
    };
  }, [getToken]);
}
