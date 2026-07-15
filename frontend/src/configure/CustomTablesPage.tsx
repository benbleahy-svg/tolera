/**
 * Configure → Custom Tables (M1.9, spec #kalk-tables): the org tables Kalk
 * `table_var`/`table_lookup` read. Create a table with typed columns
 * (boolean | numeric | string), edit rows inline (spreadsheet-style save-all),
 * or replace everything from a CSV upload. The op-def-level formula editor
 * arrives with the M1.12 library management pages; this page owns the data.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ApiError } from '../api/client';
import {
  type CellValue,
  type ColumnSpec,
  type ColumnType,
  type CustomTableDetail,
  type CustomTableOut,
  type TableRowData,
  useConfigureApi,
} from './api';

const COLUMN_TYPES: ColumnType[] = ['string', 'numeric', 'boolean'];

function CellInput({
  type,
  value,
  onChange,
}: {
  type: ColumnType;
  value: CellValue;
  onChange: (next: CellValue) => void;
}) {
  const { t } = useTranslation();
  if (type === 'boolean') {
    return (
      <select
        value={value === null ? '' : String(value)}
        onChange={(e) =>
          onChange(e.target.value === '' ? null : e.target.value === 'true')
        }
      >
        <option value="">—</option>
        <option value="true">{t('common.yes')}</option>
        <option value="false">{t('common.no')}</option>
      </select>
    );
  }
  return (
    <input
      value={value === null ? '' : String(value)}
      onChange={(e) => {
        // keep raw text while typing (a half-typed "90," must not be rewritten);
        // numeric columns parse at save (German decimal commas accepted)
        onChange(e.target.value.trim() === '' ? null : e.target.value);
      }}
    />
  );
}

/** Parse numeric-column draft strings at save; unparseable text passes through
 * so the backend rejects it with its clean `invalid_cell` 422. */
function parseRow(row: TableRowData, columns: ColumnSpec[]): TableRowData {
  const parsed: TableRowData = { ...row };
  for (const column of columns) {
    const value = parsed[column.name];
    if (column.type === 'numeric' && typeof value === 'string' && value.trim() !== '') {
      const num = Number(value.replace(',', '.'));
      if (Number.isFinite(num)) parsed[column.name] = num;
    }
  }
  return parsed;
}

export function CustomTablesPage() {
  const { t } = useTranslation();
  const api = useConfigureApi();
  const fileInput = useRef<HTMLInputElement>(null);

  const [tables, setTables] = useState<CustomTableOut[]>([]);
  const [detail, setDetail] = useState<CustomTableDetail | null>(null);
  const [rows, setRows] = useState<TableRowData[]>([]);
  const [error, setError] = useState<string | null>(null);
  // create form
  const [newName, setNewName] = useState('');
  const [newColumns, setNewColumns] = useState<ColumnSpec[]>([{ name: '', type: 'string' }]);

  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e));

  const load = useCallback(() => {
    api.listTables().then(setTables).catch(fail);
  }, [api]);
  useEffect(load, [load]);

  const open = (tableId: string) => {
    setError(null);
    api
      .getTable(tableId)
      .then((data) => {
        setDetail(data);
        setRows(data.rows.map(({ row_number: _rowNumber, ...data_ }) => data_));
      })
      .catch(fail);
  };

  const create = () => {
    setError(null);
    const columns = newColumns.filter((c) => c.name.trim() !== '');
    api
      .createTable(newName.trim(), columns)
      .then((table) => {
        setNewName('');
        setNewColumns([{ name: '', type: 'string' }]);
        load();
        open(table.id);
      })
      .catch(fail);
  };

  const saveRows = () => {
    if (!detail) return;
    setError(null);
    api
      .replaceRows(detail.id, rows.map((row) => parseRow(row, detail.columns)))
      .then((data) => {
        setDetail(data);
        setRows(data.rows.map(({ row_number: _rowNumber, ...data_ }) => data_));
        load();
      })
      .catch(fail);
  };

  const importCsv = (file: File) => {
    if (!detail) return;
    setError(null);
    api
      .importCsv(detail.id, file)
      .then(() => {
        open(detail.id);
        load();
      })
      .catch(fail);
  };

  const remove = () => {
    if (!detail) return;
    setError(null);
    api
      .deleteTable(detail.id)
      .then(() => {
        setDetail(null);
        setRows([]);
        load();
      })
      .catch(fail);
  };

  return (
    <main className="configure-page">
      <nav className="est-subnav">
        <span aria-current="page">{t('configure.custom_tables')}</span>
        <Link to="/configure/pricing">{t('configure.pricing')}</Link>
        <Link to="/configure/operations">{t('configure.operations')}</Link>
      </nav>
      <h1>{t('configure.custom_tables')}</h1>
      <p className="configure-hint">{t('configure.custom_tables_hint')}</p>
      {error && <p role="alert">{error}</p>}

      <div className="configure-layout">
        <aside>
          <ul className="configure-table-list">
            {tables.map((table) => (
              <li key={table.id}>
                <button type="button" onClick={() => open(table.id)}>
                  {table.name}{' '}
                  <span className="configure-count">
                    {t('configure.row_count', { count: table.row_count })}
                  </span>
                </button>
              </li>
            ))}
          </ul>

          <form
            className="configure-create"
            onSubmit={(e) => {
              e.preventDefault();
              create();
            }}
          >
            <h2>{t('configure.new_table')}</h2>
            <input
              aria-label={t('configure.table_name')}
              placeholder={t('configure.table_name')}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            {newColumns.map((column, index) => (
              // columns are add-only in the create form — index identity is stable
              // eslint-disable-next-line react/no-array-index-key
              <div className="configure-column-row" key={index}>
                <input
                  aria-label={t('configure.column_name')}
                  placeholder={t('configure.column_name')}
                  value={column.name}
                  onChange={(e) =>
                    setNewColumns((prev) =>
                      prev.map((c, i) => (i === index ? { ...c, name: e.target.value } : c)),
                    )
                  }
                />
                <select
                  aria-label={t('configure.column_type')}
                  value={column.type}
                  onChange={(e) =>
                    setNewColumns((prev) =>
                      prev.map((c, i) =>
                        i === index ? { ...c, type: e.target.value as ColumnType } : c,
                      ),
                    )
                  }
                >
                  {COLUMN_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {t(`configure.type_${type}`)}
                    </option>
                  ))}
                </select>
              </div>
            ))}
            <div className="configure-actions">
              <button
                type="button"
                onClick={() => setNewColumns((prev) => [...prev, { name: '', type: 'string' }])}
              >
                {t('configure.add_column')}
              </button>
              <button type="submit" disabled={newName.trim() === ''}>
                {t('configure.create_table')}
              </button>
            </div>
          </form>
        </aside>

        {detail && (
          <section aria-label={detail.name}>
            <header className="configure-table-header">
              <h2>{detail.name}</h2>
              <div className="configure-actions">
                <button type="button" onClick={() => fileInput.current?.click()}>
                  {t('configure.import_csv')}
                </button>
                <input
                  ref={fileInput}
                  type="file"
                  accept=".csv,text/csv"
                  hidden
                  aria-label={t('configure.import_csv')}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) importCsv(file);
                    e.target.value = '';
                  }}
                />
                <button
                  type="button"
                  aria-label={t('configure.export_csv_label', { name: detail.name })}
                  onClick={() => {
                    // spec #kalk-tables: tables are downloadable — client-side
                    // CSV of the loaded columns + rows (German headers as-is)
                    const quote = (v: unknown): string => {
                      if (v === null || v === undefined) return '';
                      const s =
                        typeof v === 'boolean' ? (v ? 'ja' : 'nein') : String(v);
                      return /[",;\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
                    };
                    const header = detail.columns.map((c) => quote(c.name)).join(';');
                    const lines = rows.map((r) =>
                      detail.columns.map((c) => quote(r[c.name])).join(';'),
                    );
                    const blob = new Blob([[header, ...lines].join('\n')], {
                      type: 'text/csv;charset=utf-8',
                    });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `${detail.name}.csv`;
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                >
                  {t('configure.export_csv')}
                </button>
                <button type="button" onClick={remove}>
                  {t('configure.delete_table')}
                </button>
              </div>
            </header>
            <table className="configure-grid">
              <thead>
                <tr>
                  {detail.columns.map((column) => (
                    <th key={column.name}>
                      {column.name}{' '}
                      <span className="configure-count">{t(`configure.type_${column.type}`)}</span>
                    </th>
                  ))}
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row, rowIndex) => (
                  // rows are positional until saved (row_number is assigned server-side)
                  // eslint-disable-next-line react/no-array-index-key
                  <tr key={rowIndex}>
                    {detail.columns.map((column) => (
                      <td key={column.name}>
                        <CellInput
                          type={column.type}
                          value={row[column.name] ?? null}
                          onChange={(next) =>
                            setRows((prev) =>
                              prev.map((r, i) =>
                                i === rowIndex ? { ...r, [column.name]: next } : r,
                              ),
                            )
                          }
                        />
                      </td>
                    ))}
                    <td>
                      <button
                        type="button"
                        aria-label={t('configure.remove_row')}
                        onClick={() =>
                          setRows((prev) => prev.filter((_, i) => i !== rowIndex))
                        }
                      >
                        ×
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="configure-actions">
              <button
                type="button"
                onClick={() =>
                  setRows((prev) => [
                    ...prev,
                    Object.fromEntries(detail.columns.map((c) => [c.name, null])),
                  ])
                }
              >
                {t('configure.add_row')}
              </button>
              <button type="button" onClick={saveRows}>
                {t('configure.save_rows')}
              </button>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
