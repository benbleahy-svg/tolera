/**
 * Assembly Components section (M4.10, spec #assembly; DemoO/04, DemoM/15,
 * DemoL/02+03): grouped component rows (Sub-assemblies / Manufactured /
 * Purchased) over the published BOM with FLAT BOM / CHILD BOM switch,
 * Grouped toggle, Node Qty + Flat Qty, per-break costs ("Showing rollup cost
 * to parent" in CHILD view, "cost without rollup" in FLAT), the row ⋮ menu
 * (update process/material, copy pricing, convert-to-purchased via Smart
 * Match, delete), multi-select → Bulk Update Components (deletes existing
 * operations, regenerates routers), single-level drag reorder (Grouped off),
 * ADD PURCHASED COMPONENTS from the library, and the Component Summary row.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { EstimatingApi } from './api';
import type {
  AssemblyComponentsOut,
  AssemblyNodeOut,
  ProcessOut,
  PurchaseMatchesOut,
  PurchasedComponentOut,
} from './types';

interface Props {
  api: EstimatingApi;
  quoteItemId: string;
  editable: boolean;
  formatMoney: (value: string | null) => string;
  /** bump to force a refetch (e.g. after a BOM publish) */
  refreshToken?: number;
  /** notify the page that costs changed (root reprice) */
  onChanged?: () => void;
}

function flatten(rows: AssemblyNodeOut[]): AssemblyNodeOut[] {
  const out: AssemblyNodeOut[] = [];
  const walk = (row: AssemblyNodeOut) => {
    out.push(row);
    row.children.forEach(walk);
  };
  rows.forEach(walk);
  return out;
}

function rowName(row: AssemblyNodeOut): string {
  return row.part_number ?? row.filename ?? row.description ?? '—';
}

// --------------------------------------------------------------------------- //
// Convert to Purchased Component (Smart Match) — DemoL/03
// --------------------------------------------------------------------------- //
function ConvertModal({
  api,
  componentId,
  onDone,
  onClose,
}: {
  api: EstimatingApi;
  componentId: string;
  onDone: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [matches, setMatches] = useState<PurchaseMatchesOut | null>(null);
  const [tab, setTab] = useState<'smart' | 'all'>('smart');
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState({ oem: '', price: '', description: '' });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getPurchaseMatches(componentId).then(setMatches).catch(() => setError('load'));
  }, [api, componentId]);

  const convert = async () => {
    try {
      if (creating) {
        await api.convertToPurchased(componentId, {
          create: {
            oem_part_number: draft.oem,
            piece_price: draft.price.trim() === '' ? null : draft.price.replace(',', '.'),
            description: draft.description || null,
          },
        });
      } else if (selected) {
        await api.convertToPurchased(componentId, { purchased_component_id: selected });
      } else {
        return;
      }
      onDone();
    } catch {
      setError('convert');
    }
  };

  const indicator = (ok: boolean, label: string, count?: number) => (
    <li className={ok ? 'asm-match-yes' : 'asm-match-no'}>
      <span aria-hidden="true">{ok ? '✓' : '—'}</span> {label}
      {count != null && count > 0 ? ` (${count})` : ''}
    </li>
  );

  return (
    <div className="est-modal-backdrop" role="dialog" aria-modal="true">
      <div className="est-modal asm-convert-modal">
        <header>
          <h3>{t('assembly.convert_title')}</h3>
          <button type="button" aria-label={t('common.close')} onClick={onClose}>
            ×
          </button>
        </header>
        {matches && (
          <p className="asm-convert-part">
            {t('assembly.converting', {
              name:
                matches.component.part_number ??
                matches.component.filename ??
                matches.component.id,
            })}
          </p>
        )}
        <nav className="asm-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'smart'}
            onClick={() => setTab('smart')}
          >
            {t('assembly.tab_smart')}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'all'}
            onClick={() => setTab('all')}
          >
            {t('assembly.tab_all')}
          </button>
        </nav>
        {error && <p role="alert">{t('assembly.convert_error')}</p>}
        {!creating && matches && (
          <div className="asm-match-list">
            {tab === 'smart' && (
              <>
                <h4>{t('assembly.previously_used')}</h4>
                {matches.smart.length === 0 && <p>{t('assembly.no_matches')}</p>}
                {matches.smart.map((card) => (
                  <label key={card.purchased_component.id} className="asm-match-card">
                    <input
                      type="radio"
                      name="asm-match"
                      checked={selected === card.purchased_component.id}
                      onChange={() => setSelected(card.purchased_component.id)}
                    />
                    <span className="asm-match-ids">
                      <strong>{card.purchased_component.oem_part_number}</strong>
                      {card.purchased_component.internal_part_number && (
                        <span> · {card.purchased_component.internal_part_number}</span>
                      )}
                      {card.purchased_component.brand && (
                        <span className="asm-brand-chip">{card.purchased_component.brand}</span>
                      )}
                    </span>
                    <ul className="asm-match-indicators">
                      {indicator(card.oem_part_number_match, t('assembly.match_oem_pn'))}
                      {indicator(card.oem_geometric_match, t('assembly.match_oem_geo'))}
                      {indicator(
                        card.historical_geometric_matches > 0,
                        t('assembly.match_historical'),
                        card.historical_geometric_matches,
                      )}
                    </ul>
                  </label>
                ))}
                {matches.unlinked_oem.length > 0 && (
                  <>
                    <h4>{t('assembly.unlinked_oem')}</h4>
                    <ul>
                      {matches.unlinked_oem.map((p) => (
                        <li key={p.id}>
                          {p.brand} {p.oem_part_number}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </>
            )}
            {tab === 'all' &&
              matches.all.map((pc) => (
                <label key={pc.id} className="asm-match-card">
                  <input
                    type="radio"
                    name="asm-match"
                    checked={selected === pc.id}
                    onChange={() => setSelected(pc.id)}
                  />
                  <span className="asm-match-ids">
                    <strong>{pc.oem_part_number}</strong>
                    {pc.description && <span> · {pc.description}</span>}
                  </span>
                </label>
              ))}
          </div>
        )}
        {creating && (
          <div className="asm-create-new">
            <label>
              {t('assembly.create_oem_pn')}
              <input
                value={draft.oem}
                onChange={(e) => setDraft({ ...draft, oem: e.target.value })}
              />
            </label>
            <label>
              {t('assembly.create_price')}
              <input
                value={draft.price}
                onChange={(e) => setDraft({ ...draft, price: e.target.value })}
              />
            </label>
            <label>
              {t('assembly.create_description')}
              <input
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              />
            </label>
          </div>
        )}
        <footer>
          <button type="button" onClick={() => setCreating((v) => !v)}>
            {creating ? t('assembly.back_to_matches') : t('assembly.create_new')}
          </button>
          <span className="est-modal-spacer" />
          <button type="button" onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button
            type="button"
            className="est-primary"
            disabled={creating ? draft.oem.trim() === '' : selected == null}
            onClick={convert}
          >
            {t('assembly.convert_cta')}
          </button>
        </footer>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Bulk Update Components — DemoM/15 / DemoO/06
// --------------------------------------------------------------------------- //
function BulkUpdateModal({
  api,
  componentIds,
  onDone,
  onClose,
}: {
  api: EstimatingApi;
  componentIds: string[];
  onDone: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [processes, setProcesses] = useState<ProcessOut[]>([]);
  const [processId, setProcessId] = useState('');
  const [error, setError] = useState(false);

  useEffect(() => {
    api.listProcesses().then(setProcesses).catch(() => setError(true));
  }, [api]);

  return (
    <div className="est-modal-backdrop" role="dialog" aria-modal="true">
      <div className="est-modal asm-bulk-modal">
        <header>
          <h3>{t('assembly.bulk_title')}</h3>
          <button type="button" aria-label={t('common.close')} onClick={onClose}>
            ×
          </button>
        </header>
        <label>
          {t('assembly.bulk_process')}
          <select value={processId} onChange={(e) => setProcessId(e.target.value)}>
            <option value="">{t('assembly.bulk_select_process')}</option>
            {processes.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <p className="asm-bulk-warning" role="alert">
          {t('assembly.bulk_warning')}
        </p>
        {error && <p role="alert">{t('assembly.bulk_error')}</p>}
        <footer>
          <button type="button" onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button
            type="button"
            className="est-primary"
            disabled={processId === ''}
            onClick={async () => {
              try {
                await api.bulkUpdateComponents(componentIds, processId, null);
                onDone();
              } catch {
                setError(true);
              }
            }}
          >
            {t('assembly.bulk_confirm')}
          </button>
        </footer>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// ADD PURCHASED COMPONENTS — library picker (KB purchased-components)
// --------------------------------------------------------------------------- //
function AddPurchasedModal({
  api,
  quoteItemId,
  onDone,
  onClose,
}: {
  api: EstimatingApi;
  quoteItemId: string;
  onDone: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [q, setQ] = useState('');
  const [results, setResults] = useState<PurchasedComponentOut[]>([]);
  const [chosen, setChosen] = useState<Record<string, number>>({});

  useEffect(() => {
    api.listPurchasedComponents(q).then(setResults).catch(() => setResults([]));
  }, [api, q]);

  return (
    <div className="est-modal-backdrop" role="dialog" aria-modal="true">
      <div className="est-modal asm-addpc-modal">
        <header>
          <h3>{t('assembly.addpc_title')}</h3>
          <button type="button" aria-label={t('common.close')} onClick={onClose}>
            ×
          </button>
        </header>
        <input
          placeholder={t('assembly.addpc_search')}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <ul className="asm-addpc-list">
          {results.map((pc) => (
            <li key={pc.id}>
              <label>
                <input
                  type="checkbox"
                  checked={pc.id in chosen}
                  onChange={(e) =>
                    setChosen((prev) => {
                      const next = { ...prev };
                      if (e.target.checked) next[pc.id] = 1;
                      else delete next[pc.id];
                      return next;
                    })
                  }
                />
                {pc.oem_part_number}
                {pc.description ? ` · ${pc.description}` : ''}
              </label>
              {pc.id in chosen && (
                <input
                  type="number"
                  min={1}
                  aria-label={t('assembly.addpc_qty', { name: pc.oem_part_number })}
                  value={chosen[pc.id]}
                  onChange={(e) =>
                    setChosen((prev) => ({
                      ...prev,
                      [pc.id]: Math.max(1, Number(e.target.value) || 1),
                    }))
                  }
                />
              )}
            </li>
          ))}
        </ul>
        <footer>
          <button type="button" onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button
            type="button"
            className="est-primary"
            disabled={Object.keys(chosen).length === 0}
            onClick={async () => {
              await api.addPurchasedComponents(
                quoteItemId,
                Object.entries(chosen).map(([id, qty]) => ({
                  purchased_component_id: id,
                  node_qty: qty,
                })),
              );
              onDone();
            }}
          >
            {t('assembly.addpc_confirm')}
          </button>
        </footer>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// The section
// --------------------------------------------------------------------------- //
export default function AssemblyComponentsSection({
  api,
  quoteItemId,
  editable,
  formatMoney,
  refreshToken = 0,
  onChanged,
}: Props) {
  const { t } = useTranslation();
  const [data, setData] = useState<AssemblyComponentsOut | null>(null);
  const [view, setView] = useState<'flat' | 'child'>('child');
  const [grouped, setGrouped] = useState(true);
  const [search, setSearch] = useState('');
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const [menuRow, setMenuRow] = useState<string | null>(null);
  const [convertFor, setConvertFor] = useState<string | null>(null);
  const [copyFor, setCopyFor] = useState<string | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);

  const load = useCallback(() => {
    let live = true;
    api
      .getAssemblyComponents(quoteItemId)
      .then((next) => live && setData(next))
      .catch(() => live && setData(null));
    return () => {
      live = false;
    };
  }, [api, quoteItemId]);

  useEffect(() => {
    // switching line items must never leave the previous tree interactive
    setData(null);
    setSelection(new Set());
    return load();
  }, [load, refreshToken]);

  const reload = () => {
    load();
    setSelection(new Set());
    setMenuRow(null);
    setConvertFor(null);
    setCopyFor(null);
    setBulkOpen(false);
    setAddOpen(false);
    onChanged?.();
  };

  const allRows = useMemo(() => (data ? flatten(data.tree) : []), [data]);
  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return allRows;
    return allRows.filter((r) => rowName(r).toLowerCase().includes(needle));
  }, [allRows, search]);

  if (!data || data.tree.length === 0) return null;

  const quantities = data.quantities;
  const costsOf = (row: AssemblyNodeOut) => (view === 'child' ? row.rollup_costs : row.self_costs);
  const groups: { key: 'subassembly' | 'manufactured' | 'purchased'; rows: AssemblyNodeOut[] }[] =
    [
      { key: 'subassembly', rows: visible.filter((r) => r.group === 'subassembly') },
      { key: 'manufactured', rows: visible.filter((r) => r.group === 'manufactured') },
      { key: 'purchased', rows: visible.filter((r) => r.group === 'purchased') },
    ];
  const topLevel = data.tree;

  const toggleSelect = (componentId: string | null) => {
    if (!componentId) return;
    setSelection((prev) => {
      const next = new Set(prev);
      if (next.has(componentId)) next.delete(componentId);
      else next.add(componentId);
      return next;
    });
  };

  const onDropOn = async (target: AssemblyNodeOut) => {
    if (!dragId || dragId === target.node_id || !data.root_node_id) return;
    const order = topLevel.map((r) => r.node_id);
    const from = order.indexOf(dragId);
    const to = order.indexOf(target.node_id);
    if (from < 0 || to < 0) return;
    order.splice(from, 1);
    order.splice(to, 0, dragId);
    await api.reorderAssemblyComponents(quoteItemId, data.root_node_id, order);
    setDragId(null);
    load();
  };

  const renderRow = (row: AssemblyNodeOut, depth: number) => {
    const draggable = editable && view === 'child' && !grouped && depth === 0;
    return (
      <tr
        key={row.node_id}
        className="asm-row"
        draggable={draggable}
        onDragStart={() => setDragId(row.node_id)}
        onDragOver={(e) => draggable && e.preventDefault()}
        onDrop={() => draggable && onDropOn(row)}
      >
        <td className="asm-select">
          {draggable && (
            <span className="asm-drag-handle" aria-hidden="true">
              ⠿
            </span>
          )}
          <input
            type="checkbox"
            aria-label={t('assembly.select_row', { name: rowName(row) })}
            checked={row.component_id != null && selection.has(row.component_id)}
            onChange={() => toggleSelect(row.component_id)}
          />
        </td>
        <td className="asm-name" style={{ paddingLeft: depth * 16 }}>
          {rowName(row)}
          {row.brand && <span className="asm-brand-chip">{row.brand}</span>}
        </td>
        <td className="est-num">{view === 'child' ? row.node_qty : row.flat_qty}</td>
        {costsOf(row).map((cost, i) => (
          <td key={quantities[i]} className="est-num">
            {formatMoney(cost)}
          </td>
        ))}
        <td className="asm-actions">
          <button
            type="button"
            aria-label={t('assembly.row_menu', { name: rowName(row) })}
            onClick={() => setMenuRow(menuRow === row.node_id ? null : row.node_id)}
          >
            ⋮
          </button>
          {menuRow === row.node_id && row.component_id && (
            <div className="asm-menu" role="menu">
              <span className="asm-menu-caption">{t('assembly.menu_component')}</span>
              <button
                type="button"
                role="menuitem"
                disabled={!editable}
                onClick={() => {
                  setCopyFor(row.component_id);
                  setMenuRow(null);
                }}
              >
                {t('assembly.menu_copy_pricing')}
              </button>
              {row.group === 'manufactured' && (
                <>
                  <span className="asm-menu-caption">
                    {t('assembly.menu_manufactured')}
                  </span>
                  <button
                    type="button"
                    role="menuitem"
                    disabled={!editable}
                    onClick={() => {
                      setConvertFor(row.component_id);
                      setMenuRow(null);
                    }}
                  >
                    {t('assembly.menu_convert')}
                  </button>
                </>
              )}
              <button
                type="button"
                role="menuitem"
                className="asm-menu-danger"
                disabled={!editable}
                onClick={async () => {
                  if (!row.component_id) return;
                  if (!window.confirm(t('assembly.delete_confirm', { name: rowName(row) })))
                    return;
                  await api.deleteComponent(row.component_id);
                  reload();
                }}
              >
                {t('assembly.menu_delete')}
              </button>
            </div>
          )}
        </td>
      </tr>
    );
  };

  const renderTreeRows = (rows: AssemblyNodeOut[], depth: number): React.ReactNode[] =>
    rows.flatMap((row) => {
      const needle = search.trim().toLowerCase();
      const match = !needle || rowName(row).toLowerCase().includes(needle);
      const childRows = view === 'child' ? renderTreeRows(row.children, depth + 1) : [];
      return match || childRows.length > 0 ? [renderRow(row, depth), ...childRows] : [];
    });

  return (
    <section className="est-section asm-section" aria-label={t('assembly.title')}>
      <h2>{t('assembly.title')}</h2>
      <div className="asm-toolbar">
        <input
          className="asm-search"
          placeholder={t('assembly.search')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <label className="asm-grouped-toggle">
          <input
            type="checkbox"
            checked={grouped}
            onChange={(e) => setGrouped(e.target.checked)}
          />
          {t('assembly.grouped')}
        </label>
        <div className="asm-view-switch" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={view === 'flat'}
            onClick={() => setView('flat')}
          >
            {t('assembly.flat_bom')}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === 'child'}
            onClick={() => setView('child')}
          >
            {t('assembly.child_bom')}
          </button>
        </div>
      </div>
      <p className="asm-rollup-caption">
        {view === 'child' ? t('assembly.showing_rollup') : t('assembly.showing_no_rollup')}
      </p>
      {selection.size > 0 && (
        <div className="asm-selection-bar" role="status">
          <span>{t('assembly.selected', { count: selection.size })}</span>
          <button type="button" disabled={!editable} onClick={() => setBulkOpen(true)}>
            {t('assembly.bulk_open')}
          </button>
        </div>
      )}
      <table className="est-table asm-table">
        <thead>
          <tr>
            <th />
            <th>{t('assembly.col_component')}</th>
            <th className="est-num">
              {view === 'child' ? t('assembly.col_node_qty') : t('assembly.col_flat_qty')}
            </th>
            {quantities.map((q) => (
              <th key={q} className="est-num">
                {q}
              </th>
            ))}
            <th />
          </tr>
        </thead>
        {grouped ? (
          groups.map(
            (group) =>
              group.rows.length > 0 && (
                <tbody key={group.key}>
                  <tr className="asm-group-header">
                    <td colSpan={4 + quantities.length}>
                      {t(`assembly.group_${group.key}`, { count: group.rows.length })}
                    </td>
                  </tr>
                  {group.rows.map((row) => renderRow(row, 0))}
                </tbody>
              ),
          )
        ) : (
          <tbody>{renderTreeRows(view === 'child' ? topLevel : allRows, 0)}</tbody>
        )}
        <tbody>
          <tr className="asm-summary">
            <td />
            <td>{t('assembly.summary')}</td>
            <td className="est-num">{data.summary.flat_qty_total}</td>
            {data.summary.totals.map((total, i) => (
              <td key={quantities[i]} className="est-num">
                {formatMoney(total)}
              </td>
            ))}
            <td />
          </tr>
        </tbody>
      </table>
      <div className="asm-footer-actions">
        <button type="button" disabled={!editable} onClick={() => setAddOpen(true)}>
          {t('assembly.add_purchased')}
        </button>
      </div>

      {copyFor && (
        <CopyPricingModal
          api={api}
          sourceComponentId={copyFor}
          targets={allRows.filter((r) => r.component_id && r.component_id !== copyFor)}
          onDone={reload}
          onClose={() => setCopyFor(null)}
        />
      )}
      {convertFor && (
        <ConvertModal
          api={api}
          componentId={convertFor}
          onDone={reload}
          onClose={() => setConvertFor(null)}
        />
      )}
      {bulkOpen && (
        <BulkUpdateModal
          api={api}
          componentIds={[...selection]}
          onDone={reload}
          onClose={() => setBulkOpen(false)}
        />
      )}
      {addOpen && (
        <AddPurchasedModal
          api={api}
          quoteItemId={quoteItemId}
          onDone={reload}
          onClose={() => setAddOpen(false)}
        />
      )}
    </section>
  );
}

// --------------------------------------------------------------------------- //
// Copy pricing (DemoM/17) — one source → one target, Material/Operations
// --------------------------------------------------------------------------- //
function CopyPricingModal({
  api,
  sourceComponentId,
  targets,
  onDone,
  onClose,
}: {
  api: EstimatingApi;
  sourceComponentId: string;
  targets: AssemblyNodeOut[];
  onDone: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [target, setTarget] = useState<string | null>(null);
  const [material, setMaterial] = useState(true);
  const [operations, setOperations] = useState(true);

  return (
    <div className="est-modal-backdrop" role="dialog" aria-modal="true">
      <div className="est-modal asm-copy-modal">
        <header>
          <h3>{t('assembly.copy_title')}</h3>
          <button type="button" aria-label={t('common.close')} onClick={onClose}>
            ×
          </button>
        </header>
        <label>
          <input
            type="checkbox"
            checked={material}
            onChange={(e) => setMaterial(e.target.checked)}
          />
          {t('assembly.copy_material')}
        </label>
        <label>
          <input
            type="checkbox"
            checked={operations}
            onChange={(e) => setOperations(e.target.checked)}
          />
          {t('assembly.copy_operations')}
        </label>
        <h4>{t('assembly.copy_target')}</h4>
        <ul className="asm-copy-targets">
          {targets.map((row) => (
            <li key={row.node_id}>
              <label>
                <input
                  type="radio"
                  name="asm-copy-target"
                  checked={target === row.component_id}
                  onChange={() => setTarget(row.component_id)}
                />
                {rowName(row)}
              </label>
            </li>
          ))}
        </ul>
        <footer>
          <button type="button" onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button
            type="button"
            className="est-primary"
            disabled={target == null || (!material && !operations)}
            onClick={async () => {
              if (!target) return;
              await api.copyPricing(sourceComponentId, target, material, operations);
              onDone();
            }}
          >
            {t('assembly.copy_cta')}
          </button>
        </footer>
      </div>
    </div>
  );
}
