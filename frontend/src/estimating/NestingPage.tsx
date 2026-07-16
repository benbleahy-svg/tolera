/**
 * Nesting Overview (M4.3, spec #nesting; DemoA/11-12, DemoJ): sheet-metal
 * components across the quote's line items grouped with their interrogated
 * flat data, a Linear Metal stub tab, "Your Nests", the prepare-nest dialog
 * (per-break stock + nest/pricing settings + the lock warning), and the Nest
 * result object (aggregate metrics + components-in-nest + schematic layout).
 * Metric-native (mm/mm²) and EUR-formatted per the DACH delta.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { useEstimatingApi } from './api';
import type {
  NestCreateBody,
  NestOut,
  NestingOverview,
  NestingOverviewRow,
} from './types';

const DEFAULT_STOCK = { length_mm: 3000, width_mm: 1500, erp_code: '', sheet_cost: '' };
const DEFAULT_SETTINGS = {
  edge_buffer_mm: 3.0,
  clearance_mm: 3.0,
  kerf_mm: 0.25,
  drop_threshold_pct: 25.0,
  distribution_method: 'area_of_parts',
};

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value == null) return '—';
  return value.toLocaleString('de-DE', { maximumFractionDigits: digits });
}

/** Schematic sheet layout — estimation-grade, a grid suggestion, not a true
 * placement (the spec's v1 ceiling: area packing, no 2D bin-packing). */
function SheetSchematic({ partsPerSheet }: { partsPerSheet: number }) {
  const count = Math.max(0, Math.min(partsPerSheet, 60));
  const cols = 10;
  return (
    <svg viewBox="0 0 200 100" className="nest-schematic" role="img" aria-hidden>
      <rect x="1" y="1" width="198" height="98" fill="none" stroke="currentColor" />
      {Array.from({ length: count }, (_, i) => (
        <rect
          key={i}
          x={4 + (i % cols) * 19.4}
          y={4 + Math.floor(i / cols) * 15.5}
          width="17"
          height="13"
          fill="currentColor"
          opacity="0.35"
        />
      ))}
    </svg>
  );
}

export function NestingPage() {
  const { quoteId } = useParams<{ quoteId: string }>();
  const { t, i18n } = useTranslation();
  const api = useEstimatingApi();

  const [overview, setOverview] = useState<NestingOverview | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [allowMixed, setAllowMixed] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [openNestId, setOpenNestId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fail = useCallback((e: unknown) => {
    setError(e instanceof ApiError ? e.message : String(e));
  }, []);

  const reload = useCallback(() => {
    if (!quoteId) return;
    api.getNestingOverview(quoteId).then(setOverview).catch(fail);
  }, [api, quoteId, fail]);

  useEffect(reload, [reload]);

  const rows = overview?.sheet_metal ?? [];
  const selectedRows = rows.filter((r) => selected.has(r.component_id));

  const formatMoney = useCallback(
    (value: string | null | undefined, currency = 'EUR'): string => {
      if (value == null) return '—';
      const amount = Number(value);
      if (Number.isNaN(amount)) return value;
      return new Intl.NumberFormat(i18n.language === 'de' ? 'de-DE' : 'en-IE', {
        style: 'currency',
        currency,
      }).format(amount);
    },
    [i18n.language],
  );

  const toggle = (row: NestingOverviewRow) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(row.component_id)) next.delete(row.component_id);
      else next.add(row.component_id);
      return next;
    });
  };

  // Selection compatibility hint (the server re-validates authoritatively):
  // like material always; like thickness unless the toggle is on.
  const selectable = (row: NestingOverviewRow): boolean => {
    if (!row.eligible || row.nest_id != null) return false;
    const anchor = selectedRows[0];
    if (!anchor || anchor.component_id === row.component_id) return true;
    if (row.material_id !== anchor.material_id) return false;
    // the prepare dialog builds one stock row per break of the anchor — a
    // mismatched break set would silently omit required stock rows
    if (row.quantities.join('/') !== anchor.quantities.join('/')) return false;
    if (allowMixed) return true;
    return (
      row.thickness_mm != null &&
      anchor.thickness_mm != null &&
      Math.abs(row.thickness_mm - anchor.thickness_mm) <= 0.01
    );
  };

  const openNest = overview?.nests.find((n) => n.id === openNestId) ?? null;

  if (!quoteId) return null;

  return (
    <main className="est-page nesting-page">
      <header className="est-header">
        <div>
          <p className="nesting-breadcrumb">
            <Link to={`/quotes/${quoteId}`}>{t('nesting.back_to_quote')}</Link>
          </p>
          <h2>{t('nesting.title')}</h2>
        </div>
        <nav className="nesting-tabs" aria-label={t('nesting.title')}>
          <span className="nesting-tab active">
            {t('nesting.sheet_metal_tab', { count: rows.length })}
          </span>
          <span className="nesting-tab" aria-disabled>
            {t('nesting.linear_tab', { count: overview?.linear_metal.length ?? 0 })}
          </span>
        </nav>
      </header>

      {error && (
        <p className="est-error" role="alert">
          {error}
        </p>
      )}

      <label className="nesting-mixed-toggle">
        <input
          type="checkbox"
          checked={allowMixed}
          onChange={(e) => {
            const on = e.target.checked;
            setAllowMixed(on);
            if (!on) {
              // prune selections that are only valid under mixed thickness
              setSelected((prev) => {
                const kept = rows.filter((r) => prev.has(r.component_id));
                const anchor = kept[0];
                if (!anchor) return prev;
                return new Set(
                  kept
                    .filter(
                      (r) =>
                        r.thickness_mm != null &&
                        anchor.thickness_mm != null &&
                        Math.abs(r.thickness_mm - anchor.thickness_mm) <= 0.01,
                    )
                    .map((r) => r.component_id),
                );
              });
            }
          }}
        />
        {t('nesting.allow_mixed_thickness')}
      </label>

      <table className="nesting-table">
        <thead>
          <tr>
            <th />
            <th>{t('nesting.col_component')}</th>
            <th>{t('nesting.col_nested')}</th>
            <th>{t('nesting.col_material')}</th>
            <th>{t('nesting.col_flat_dims')}</th>
            <th>{t('nesting.col_flat_area')}</th>
            <th>{t('nesting.col_contour')}</th>
            <th>{t('nesting.col_thickness')}</th>
            <th>{t('nesting.col_quantities')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.component_id}>
              <td>
                <input
                  type="checkbox"
                  aria-label={row.part_number ?? row.part_name ?? row.component_id}
                  checked={selected.has(row.component_id)}
                  disabled={!selectable(row)}
                  onChange={() => toggle(row)}
                />
              </td>
              <td>
                {row.part_number ?? row.part_name ?? '—'}
                {!row.eligible && (
                  <span className="nesting-ineligible"> {t('nesting.not_eligible')}</span>
                )}
              </td>
              <td>
                {row.nest_id ? (
                  <button
                    type="button"
                    className="nesting-nested-link"
                    onClick={() => setOpenNestId(row.nest_id)}
                  >
                    {row.nest_label ?? '✓'}
                  </button>
                ) : (
                  '—'
                )}
              </td>
              <td>{row.material_name ?? '—'}</td>
              <td>
                {row.flat_x_mm != null && row.flat_y_mm != null
                  ? `${formatNumber(row.flat_x_mm)} × ${formatNumber(row.flat_y_mm)}`
                  : '—'}
              </td>
              <td>{formatNumber(row.flat_area_mm2)}</td>
              <td>{formatNumber(row.contour_length_mm)}</td>
              <td>{formatNumber(row.thickness_mm, 3)}</td>
              <td>{row.make_quantities.join(' / ')}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <section className="nesting-your-nests">
        <h3>{t('nesting.your_nests')}</h3>
        {(overview?.nests.length ?? 0) === 0 ? (
          <p className="nesting-empty">{t('nesting.no_nests')}</p>
        ) : (
          <ul>
            {overview?.nests.map((nest) => (
              <li key={nest.id}>
                <button type="button" onClick={() => setOpenNestId(nest.id)}>
                  {nest.label} · {formatMoney(nest.result?.material_cost, nest.result?.currency)}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {selectedRows.length > 0 && (
        <footer className="nesting-footer" role="status">
          <span>
            {t('nesting.selected_footer', {
              count: selectedRows.length,
              thickness: formatNumber(selectedRows[0].thickness_mm, 3),
              material: selectedRows[0].material_name ?? '—',
              items: new Set(selectedRows.map((r) => r.item_id)).size,
            })}
          </span>
          <button type="button" onClick={() => setPreparing(true)}>
            {t('nesting.prepare_button')}
          </button>
        </footer>
      )}

      {preparing && (
        <PrepareNestDialog
          rows={selectedRows}
          allowMixed={allowMixed}
          onGenerate={(body) => {
            setError(null);
            return api
              .createNest(quoteId, body)
              .then(() => {
                setPreparing(false);
                setSelected(new Set());
                reload();
              })
              .catch(fail);
          }}
          onClose={() => setPreparing(false)}
        />
      )}

      {openNest && (
        <NestResultView
          nest={openNest}
          rows={rows}
          formatMoney={formatMoney}
          onDelete={() => {
            setError(null);
            api
              .deleteNest(quoteId, openNest.id)
              .then(() => {
                setOpenNestId(null);
                reload();
              })
              .catch(fail);
          }}
          onClose={() => setOpenNestId(null)}
        />
      )}
    </main>
  );
}

function PrepareNestDialog({
  rows,
  allowMixed,
  onGenerate,
  onClose,
}: {
  rows: NestingOverviewRow[];
  allowMixed: boolean;
  onGenerate: (body: NestCreateBody) => Promise<unknown>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  // Across-items nests have one shared break; same-item multi-break nests get
  // one stock row per break (DemoJ/07).
  const breaks = rows[0]?.quantities ?? [];
  const [stock, setStock] = useState(() =>
    breaks.map((quantity) => ({ quantity, ...DEFAULT_STOCK })),
  );
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [submitting, setSubmitting] = useState(false);

  // German-first: accept a comma decimal ("250,00") and normalize for the API
  const normalizeCost = (value: string) => value.trim().replace(',', '.');

  const valid = useMemo(
    () =>
      stock.every(
        (s) =>
          Number.isFinite(s.length_mm) &&
          s.length_mm > 0 &&
          Number.isFinite(s.width_mm) &&
          s.width_mm > 0 &&
          s.sheet_cost !== '' &&
          Number(normalizeCost(s.sheet_cost)) >= 0 &&
          !Number.isNaN(Number(normalizeCost(s.sheet_cost))),
      ) &&
      Number.isFinite(settings.edge_buffer_mm) &&
      settings.edge_buffer_mm >= 0 &&
      Number.isFinite(settings.clearance_mm) &&
      settings.clearance_mm >= 0 &&
      Number.isFinite(settings.kerf_mm) &&
      settings.kerf_mm >= 0 &&
      Number.isFinite(settings.drop_threshold_pct) &&
      settings.drop_threshold_pct >= 0 &&
      settings.drop_threshold_pct <= 100,
    [stock, settings],
  );

  const patchStock = (index: number, patch: Partial<(typeof stock)[number]>) => {
    setStock((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  };

  return (
    <div className="est-modal-backdrop" role="dialog" aria-label={t('nesting.dialog_title')}>
      <div className="est-modal nesting-dialog">
        <h3>{t('nesting.dialog_title')}</h3>

        <h4>{t('nesting.stock_heading')}</h4>
        <table className="nesting-stock-table">
          <thead>
            <tr>
              <th>{t('nesting.stock_quantity')}</th>
              <th>{t('nesting.stock_length')}</th>
              <th>{t('nesting.stock_width')}</th>
              <th>{t('nesting.stock_erp')}</th>
              <th>{t('nesting.stock_cost')}</th>
            </tr>
          </thead>
          <tbody>
            {stock.map((row, index) => (
              <tr key={row.quantity}>
                <td>{row.quantity}</td>
                <td>
                  <input
                    type="number"
                    aria-label={`${t('nesting.stock_length')} ${row.quantity}`}
                    value={row.length_mm}
                    onChange={(e) => patchStock(index, { length_mm: Number(e.target.value) })}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    aria-label={`${t('nesting.stock_width')} ${row.quantity}`}
                    value={row.width_mm}
                    onChange={(e) => patchStock(index, { width_mm: Number(e.target.value) })}
                  />
                </td>
                <td>
                  <input
                    type="text"
                    aria-label={`${t('nesting.stock_erp')} ${row.quantity}`}
                    value={row.erp_code}
                    onChange={(e) => patchStock(index, { erp_code: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    type="text"
                    inputMode="decimal"
                    aria-label={`${t('nesting.stock_cost')} ${row.quantity}`}
                    value={row.sheet_cost}
                    placeholder="250.00"
                    onChange={(e) => patchStock(index, { sheet_cost: e.target.value })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <h4>{t('nesting.settings_heading')}</h4>
        <div className="nesting-settings-grid">
          <label>
            {t('nesting.edge_buffer')}
            <input
              type="number"
              step="0.1"
              value={settings.edge_buffer_mm}
              onChange={(e) =>
                setSettings((s) => ({ ...s, edge_buffer_mm: Number(e.target.value) }))
              }
            />
          </label>
          <label>
            {t('nesting.clearance')}
            <input
              type="number"
              step="0.1"
              value={settings.clearance_mm}
              onChange={(e) =>
                setSettings((s) => ({ ...s, clearance_mm: Number(e.target.value) }))
              }
            />
          </label>
          <label>
            {t('nesting.kerf')}
            <input
              type="number"
              step="0.05"
              value={settings.kerf_mm}
              onChange={(e) => setSettings((s) => ({ ...s, kerf_mm: Number(e.target.value) }))}
            />
          </label>
        </div>

        <h4>{t('nesting.pricing_heading')}</h4>
        <div className="nesting-settings-grid">
          <label>
            {t('nesting.distribution')}
            <select value={settings.distribution_method} disabled>
              <option value="area_of_parts">{t('nesting.distribution_area')}</option>
            </select>
          </label>
          <label>
            {t('nesting.drop_threshold')}
            <input
              type="number"
              step="1"
              min="0"
              max="100"
              value={settings.drop_threshold_pct}
              onChange={(e) =>
                setSettings((s) => ({ ...s, drop_threshold_pct: Number(e.target.value) }))
              }
            />
          </label>
        </div>

        <p className="nesting-lock-warning" role="note">
          ⓘ {t('nesting.lock_warning')}
        </p>

        <div className="est-actions">
          <button type="button" onClick={onClose}>
            {t('nesting.cancel')}
          </button>
          <button
            type="button"
            disabled={!valid || submitting}
            onClick={() => {
              // the POST is not idempotent — block a double-click resubmit
              setSubmitting(true);
              void onGenerate({
                component_ids: rows.map((r) => r.component_id),
                stock: stock.map((s) => ({ ...s, sheet_cost: normalizeCost(s.sheet_cost) })),
                settings: { ...settings, allow_mixed_thickness: allowMixed },
                component_settings: [],
              }).finally(() => setSubmitting(false));
            }}
          >
            {t('nesting.generate')}
          </button>
        </div>
      </div>
    </div>
  );
}

function NestResultView({
  nest,
  rows,
  formatMoney,
  onDelete,
  onClose,
}: {
  nest: NestOut;
  rows: NestingOverviewRow[];
  formatMoney: (value: string | null | undefined, currency?: string) => string;
  onDelete: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const result = nest.result;
  const stock = nest.config?.stock;
  const total =
    (result?.used_area_mm2 ?? 0) + (result?.scrap_area_mm2 ?? 0) + (result?.drop_area_mm2 ?? 0);
  const pct = (v: number) => (total > 0 ? `${((v / total) * 100).toFixed(1)} %` : '—');
  const rowByComponent = new Map(rows.map((r) => [r.component_id, r]));
  const setSize = nest.set_id ? rows.length : 0; // display only

  return (
    <div className="est-modal-backdrop" role="dialog" aria-label={nest.label ?? 'Nest'}>
      <div className="est-modal nesting-result">
        <header className="nesting-result-header">
          <div>
            <h3>{nest.label}</h3>
            {stock && (
              <p className="nesting-stock-line">
                {t('nesting.nest_stock_line', {
                  length: formatNumber(stock.length_mm),
                  width: formatNumber(stock.width_mm),
                  thickness: formatNumber(nest.config?.thickness_mm ?? null, 3),
                  material:
                    rowByComponent.get(nest.config?.component_ids?.[0] ?? '')?.material_name ??
                    '—',
                })}
              </p>
            )}
          </div>
          <div className="nesting-result-actions">
            <button type="button" onClick={onDelete}>
              {t('nesting.delete_nest')}
            </button>
            <button type="button" onClick={onClose} aria-label={t('nesting.cancel')}>
              ✕
            </button>
          </div>
        </header>

        {result && (
          <>
            <dl className="nesting-metrics">
              <div>
                <dt>{t('nesting.total_sheets')}</dt>
                <dd>{formatNumber(result.charged_sheets, 4)}</dd>
              </div>
              <div>
                <dt>{t('nesting.total_cost')}</dt>
                <dd>{formatMoney(result.material_cost, result.currency)}</dd>
              </div>
              <div>
                <dt>{t('nesting.used_area')}</dt>
                <dd>
                  {formatNumber(result.used_area_mm2)} mm² ({pct(result.used_area_mm2)})
                </dd>
              </div>
              <div>
                <dt>{t('nesting.scrap_area')}</dt>
                <dd>
                  {formatNumber(result.scrap_area_mm2)} mm² ({pct(result.scrap_area_mm2)})
                </dd>
              </div>
              <div>
                <dt>{t('nesting.drop_area')}</dt>
                <dd>
                  {formatNumber(result.drop_area_mm2)} mm² ({pct(result.drop_area_mm2)})
                </dd>
              </div>
              <div>
                <dt>{t('nesting.total_contour')}</dt>
                <dd>{formatNumber(result.total_contour_length_mm)} mm</dd>
              </div>
            </dl>

            <SheetSchematic partsPerSheet={result.components[0]?.parts_per_sheet ?? 0} />

            <h4>{t('nesting.components_in_nest', { count: result.components.length })}</h4>
            <table className="nesting-components-table">
              <thead>
                <tr>
                  <th>{t('nesting.col_component')}</th>
                  <th>{t('nesting.parts_per_sheet')}</th>
                  <th>{t('nesting.cost_share')}</th>
                  <th>{t('nesting.allocated_cost')}</th>
                </tr>
              </thead>
              <tbody>
                {result.components.map((comp) => {
                  const row = rowByComponent.get(comp.component_id);
                  return (
                    <tr key={comp.component_id}>
                      <td>{row?.part_number ?? row?.part_name ?? comp.component_id}</td>
                      <td>{formatNumber(comp.parts_per_sheet, 0)}</td>
                      <td>{comp.cost_share_pct} %</td>
                      <td>{formatMoney(comp.allocated_cost, result.currency)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {setSize > 1 && null}
          </>
        )}
      </div>
    </div>
  );
}
