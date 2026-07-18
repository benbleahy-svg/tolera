/**
 * Quotes list — the `/quotes` destination (spec #quoteslist). A two-pane screen:
 * a left "Quotes & Line Items" saved-view sidebar (computed system views + the
 * user's custom views) and a right TanStack-Table grid titled by the active view,
 * with a status filter, active-filter chips, a Save-view control, and pagination.
 *
 * The list is read-only in M1.3 (quotes are created in M1.4); the CREATE QUOTE
 * button is shown disabled to editors to preserve the intended layout. Selecting a
 * saved view replays its stored filters — the same body the search endpoint takes.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';

import { ApiError } from '../api/client';
import { useHasPermission } from '../session/session';
import { useQuotesApi } from './api';
import type {
  FilterClause,
  QuoteRow,
  QuoteSearchRequest,
  QuoteSearchResponse,
  QuoteStatus,
  SavedView,
  SavedViewList,
  SortClause,
} from './types';

const PAGE_SIZE = 20;
const STATUSES: QuoteStatus[] = ['draft', 'sent', 'won', 'lost', 'expired'];

/** What the grid is currently showing — drives both the request and the title. */
type Active =
  | { kind: 'system'; key: string }
  | { kind: 'custom'; id: string }
  | { kind: 'adhoc' };

const columnHelper = createColumnHelper<QuoteRow>();

export function QuotesPage() {
  const { t, i18n } = useTranslation();
  const api = useQuotesApi();
  const canEdit = useHasPermission('quote_edit');

  const [views, setViews] = useState<SavedViewList>({ system: [], custom: [] });
  const [active, setActive] = useState<Active>({ kind: 'system', key: 'all-quotes' });
  const [filters, setFilters] = useState<FilterClause[]>([]);
  const [sort, setSort] = useState<SortClause[]>([]);
  const [data, setData] = useState<QuoteSearchResponse | null>(null);
  const [page, setPage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [savingView, setSavingView] = useState(false);
  const [newViewName, setNewViewName] = useState('');
  // M5.0 — quotes-list multi-select + Bulk Refresh Pricing.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkMsg, setBulkMsg] = useState<string | null>(null);
  const requestSeq = useRef(0);

  // ----------------------------------------------------------------- search
  const runSearch = useCallback(
    (req: QuoteSearchRequest) => {
      const seq = ++requestSeq.current;
      setError(null);
      api
        .searchQuotes({ ...req, limit: PAGE_SIZE })
        .then((next) => {
          if (seq === requestSeq.current) setData(next);
        })
        .catch((e: unknown) => {
          if (seq === requestSeq.current) {
            setError(e instanceof ApiError ? e.message : String(e));
          }
        });
    },
    [api],
  );

  /** Build the request from the explicit selection + clauses (never re-looks-up a
   * saved view — so a just-created view searches correctly before its row lands in
   * `views` state). A system view is server-computed; everything else replays its
   * stored/edited filters + sort. */
  const requestFor = useCallback(
    (
      next: Active,
      nextFilters: FilterClause[],
      nextSort: SortClause[],
      nextPage: number,
    ): QuoteSearchRequest => {
      const offset = nextPage * PAGE_SIZE;
      if (next.kind === 'system') return { system_view: next.key, offset };
      return { filters: nextFilters, sort: nextSort, offset };
    },
    [],
  );

  const apply = useCallback(
    (next: Active, nextFilters: FilterClause[], nextSort: SortClause[], nextPage: number) => {
      setActive(next);
      setFilters(nextFilters);
      setSort(nextSort);
      setPage(nextPage);
      setSelected(new Set()); // a new view/page/filter drops the stale selection
      setBulkMsg(null);
      runSearch(requestFor(next, nextFilters, nextSort, nextPage));
    },
    [runSearch, requestFor],
  );

  // ----------------------------------------------------------- saved views
  const loadViews = useCallback(
    () => api.listSavedViews().then(setViews).catch(() => undefined),
    [api],
  );

  useEffect(() => {
    void loadViews();
    runSearch(requestFor({ kind: 'system', key: 'all-quotes' }, [], [], 0));
    // Run once on mount; subsequent loads go through the handlers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectSystem = (key: string) => apply({ kind: 'system', key }, [], [], 0);
  const selectCustom = (view: SavedView) =>
    apply({ kind: 'custom', id: view.id }, view.filters, view.sort, 0);

  const setStatusFilter = (status: string) => {
    const next: FilterClause[] = status ? [{ field: 'status', op: 'eq', value: status }] : [];
    apply({ kind: 'adhoc' }, next, sort, 0);
  };

  const removeFilter = (index: number) =>
    apply({ kind: 'adhoc' }, filters.filter((_, i) => i !== index), sort, 0);

  const goToPage = (nextPage: number) => apply(active, filters, sort, nextPage);

  const saveView = () => {
    const name = newViewName.trim();
    if (!name) return;
    api
      .createSavedView({ name, filters, sort })
      .then(async (created) => {
        setSavingView(false);
        setNewViewName('');
        await loadViews();
        apply({ kind: 'custom', id: created.id }, created.filters, created.sort, 0);
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  };

  const deleteView = (view: SavedView) => {
    api
      .deleteSavedView(view.id)
      .then(async () => {
        await loadViews();
        if (active.kind === 'custom' && active.id === view.id) selectSystem('all-quotes');
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  };

  // ------------------------------------------------ multi-select + bulk refresh
  const rows = data?.rows ?? [];
  const toggleRow = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const allOnPageSelected = rows.length > 0 && rows.every((r) => selected.has(r.id));
  const toggleAllOnPage = () =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (allOnPageSelected) rows.forEach((r) => next.delete(r.id));
      else rows.forEach((r) => next.add(r.id));
      return next;
    });

  const runBulkRefresh = () => {
    const ids = [...selected];
    if (ids.length === 0) return;
    // Capture the current search generation: if the user changes view/filter/page
    // while the refresh runs, don't let our reflect-search clobber their newer view.
    const searchSeqAtStart = requestSeq.current;
    setBulkBusy(true);
    setBulkMsg(null);
    setError(null);
    api
      .bulkRefreshPricing(ids)
      .then((r) => {
        setBulkMsg(
          r.mode === 'async'
            ? t('quotes.bulk_refresh_queued', { count: r.quote_count ?? ids.length })
            : t('quotes.bulk_refresh_done', { count: r.refreshed_quotes ?? 0 }),
        );
        setSelected(new Set());
        // Only re-search if the user hasn't navigated to a different view meanwhile.
        if (requestSeq.current === searchSeqAtStart) {
          runSearch(requestFor(active, filters, sort, page)); // reflect any repriced rows
        }
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)))
      .finally(() => setBulkBusy(false));
  };

  // -------------------------------------------------------------- the grid
  const columns = useMemo(
    () => [
      columnHelper.accessor('number', {
        header: () => t('quotes.col.number'),
        // Opens the estimating view at the spec route (M5.0); EstimatingPage resolves
        // the first line item, so no line-item id is needed here.
        cell: (info) => <Link to={`/quotes/edit/${info.row.original.id}`}>{info.getValue()}</Link>,
      }),
      columnHelper.accessor('rfq_number', {
        header: () => t('quotes.col.rfq'),
        cell: (info) => info.getValue() ?? '—',
      }),
      columnHelper.accessor('status', {
        header: () => t('quotes.col.status'),
        cell: (info) => <span className="crm-chip">{t(`quotes.status.${info.getValue()}`)}</span>,
      }),
      columnHelper.display({
        id: 'priority',
        header: () => t('quotes.col.priority'),
        // M5.0 — the derived MAX(line-item priority); blank quotes render "—".
        // German locale per the number-formatting guideline.
        cell: ({ row }) =>
          row.original.priority == null
            ? '—'
            : row.original.priority.toLocaleString(i18n.language === 'de' ? 'de-DE' : 'en-IE'),
      }),
      columnHelper.accessor('account_id', {
        header: () => t('quotes.col.account'),
        cell: (info) => info.getValue() ?? '—',
      }),
      columnHelper.accessor('salesperson_id', {
        header: () => t('quotes.col.salesperson'),
        cell: (info) => info.getValue() ?? '—',
      }),
      columnHelper.accessor('created_at', {
        header: () => t('quotes.col.created'),
        cell: (info) => new Date(info.getValue()).toLocaleDateString(i18n.language),
      }),
    ],
    [t, i18n.language],
  );

  const table = useReactTable({
    data: data?.rows ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  const total = data?.total ?? 0;
  const offset = page * PAGE_SIZE;
  const activeStatus =
    active.kind === 'adhoc'
      ? (filters.find((f) => f.field === 'status' && f.op === 'eq')?.value as string | undefined)
      : undefined;

  const title =
    active.kind === 'system'
      ? t(views.system.find((v) => v.key === active.key)?.label_key ?? 'quotes.views.all')
      : active.kind === 'custom'
        ? (views.custom.find((v) => v.id === active.id)?.name ?? '')
        : t('quotes.views.filtered');

  return (
    <section className="page quotes-page">
      <aside className="quotes-sidebar" aria-label={t('quotes.sidebar_title')}>
        <h2 className="quotes-sidebar-title">{t('quotes.sidebar_title')}</h2>
        <nav className="quotes-views" aria-label={t('quotes.section.quotes')}>
          <p className="quotes-views-heading">{t('quotes.section.quotes')}</p>
          {views.system.map((v) => (
            <button
              key={v.key}
              type="button"
              className={
                'quotes-view' +
                (active.kind === 'system' && active.key === v.key ? ' is-active' : '')
              }
              onClick={() => selectSystem(v.key)}
            >
              {t(v.label_key)}
            </button>
          ))}
          {views.custom.map((v) => (
            <div key={v.id} className="quotes-view-row">
              <button
                type="button"
                className={
                  'quotes-view' + (active.kind === 'custom' && active.id === v.id ? ' is-active' : '')
                }
                onClick={() => selectCustom(v)}
              >
                {v.name}
              </button>
              <button
                type="button"
                className="quotes-view-delete"
                aria-label={t('quotes.delete_view', { name: v.name })}
                onClick={() => deleteView(v)}
              >
                ✕
              </button>
            </div>
          ))}
        </nav>
        <p className="quotes-views-heading quotes-views-muted">
          {t('quotes.section.line_items')}
          <span className="quotes-soon">{t('quotes.section.line_items_hint')}</span>
        </p>
      </aside>

      <div className="quotes-main">
        <div className="crm-header">
          <h1 className="page-title">{title}</h1>
          {canEdit && (
            <button
              type="button"
              className="btn btn-primary"
              disabled
              title={t('quotes.create_disabled_hint')}
            >
              {t('quotes.create_quote')}
            </button>
          )}
        </div>

        <div className="crm-toolbar">
          <label className="quotes-filter">
            <span>{t('quotes.filter.status_label')}</span>
            <select
              className="crm-search quotes-status-select"
              value={activeStatus ?? ''}
              aria-label={t('quotes.filter.status_label')}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">{t('quotes.filter.all_statuses')}</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {t(`quotes.status.${s}`)}
                </option>
              ))}
            </select>
          </label>

          {filters.map((f, i) => (
            <span key={`${f.field}-${i}`} className="quotes-chip">
              {t(`quotes.col.${f.field === 'status' ? 'status' : f.field}`)}: {String(f.value)}
              <button
                type="button"
                className="quotes-chip-remove"
                aria-label={t('quotes.remove_filter')}
                onClick={() => removeFilter(i)}
              >
                ✕
              </button>
            </span>
          ))}

          {canEdit && (
            <button
              type="button"
              className="btn btn-ghost quotes-bulk-refresh"
              disabled={selected.size === 0 || bulkBusy}
              onClick={runBulkRefresh}
            >
              {selected.size > 0
                ? t('quotes.bulk_refresh_n', { count: selected.size })
                : t('quotes.bulk_refresh')}
            </button>
          )}

          {savingView ? (
            <span className="quotes-save">
              <input
                className="crm-search"
                value={newViewName}
                placeholder={t('quotes.save_view_placeholder')}
                aria-label={t('quotes.save_view_placeholder')}
                onChange={(e) => setNewViewName(e.target.value)}
              />
              <button type="button" className="btn btn-primary" onClick={saveView}>
                {t('quotes.save')}
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => setSavingView(false)}>
                {t('quotes.cancel')}
              </button>
            </span>
          ) : (
            <button type="button" className="btn btn-ghost" onClick={() => setSavingView(true)}>
              {t('quotes.save_view')}
            </button>
          )}
        </div>

        {error && (
          <p className="crm-error" role="alert">
            {error}
          </p>
        )}

        {bulkMsg && (
          <p className="quotes-bulk-msg" role="status">
            {bulkMsg}
          </p>
        )}

        {total === 0 ? (
          <p className="page-empty">{t('quotes.empty')}</p>
        ) : (
          <>
            <table className="crm-table">
              <thead>
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {canEdit && (
                      <th className="quotes-select-col">
                        <input
                          type="checkbox"
                          aria-label={t('quotes.select_all')}
                          checked={allOnPageSelected}
                          onChange={toggleAllOnPage}
                        />
                      </th>
                    )}
                    {hg.headers.map((header) => (
                      <th key={header.id}>
                        {flexRender(header.column.columnDef.header, header.getContext())}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((row) => (
                  <tr key={row.id}>
                    {canEdit && (
                      <td className="quotes-select-col">
                        <input
                          type="checkbox"
                          aria-label={t('quotes.select_row', { number: row.original.number })}
                          checked={selected.has(row.original.id)}
                          onChange={() => toggleRow(row.original.id)}
                        />
                      </td>
                    )}
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="quotes-footer">
              <span>
                {t('quotes.footer', {
                  from: total === 0 ? 0 : offset + 1,
                  to: Math.min(offset + PAGE_SIZE, total),
                  total,
                })}
              </span>
              <span className="quotes-pager">
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={page === 0}
                  onClick={() => goToPage(page - 1)}
                >
                  {t('quotes.prev')}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => goToPage(page + 1)}
                >
                  {t('quotes.next')}
                </button>
              </span>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
