/**
 * Orders list — the `/orders` destination (spec #orderslist). All orders placed
 * against won quotes: created by buyer-portal checkout (M5.2) or internal Build
 * Order (M5.7). There is **no CREATE ORDER button** — orders are never created
 * here — and **no status lifecycle** (status is ERP-owned; the only shipment state
 * is a nullable `shipped_at`).
 *
 * System-view tabs (All / Buyer Portal / Facilitated / Awaiting Shipment) are
 * server-computed; the toolbar adds a free-text search (order # / quote # / PO /
 * account), a Date-Placed range and an Account filter. Applying a range/account
 * filter switches off the system view (server-side they're mutually exclusive,
 * matching the M1.3 quotes engine); the search composes with either. Per-row ⋮
 * actions: open the source quote, open order detail, Edit order (only when the
 * shop enabled Facilitate Order Updates and the order has no shipment — the drawer
 * itself is M5.7), and Download order PDF (the M5.4 order-confirmation variant).
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
import { useCrmApi, type Account } from '../contacts/api';
import { formatMinor } from '../portal/money';
import { formatOrderDate, orderDateLocale } from './dates';
import { useOrdersApi } from './api';
import type {
  OrderFilterClause,
  OrderRow,
  OrderSearchRequest,
  OrderSearchResponse,
  OrderSystemView,
} from './types';

const PAGE_SIZE = 20;

/** The default system views, shown before the first response lands (the server
 *  echoes the authoritative list on every response). */
const INITIAL_VIEWS: OrderSystemView[] = [
  { key: 'all-orders', label_key: 'orders.views.all', is_default: true },
  { key: 'buyer-portal', label_key: 'orders.views.buyer_portal', is_default: false },
  { key: 'facilitated', label_key: 'orders.views.facilitated', is_default: false },
  { key: 'awaiting-shipment', label_key: 'orders.views.awaiting_shipment', is_default: false },
];

type Active = { kind: 'system'; key: string } | { kind: 'adhoc' };

const columnHelper = createColumnHelper<OrderRow>();

/** Trigger a browser download of a Blob under `filename`. */
function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function OrdersPage() {
  const { t, i18n } = useTranslation();
  const api = useOrdersApi();
  const crm = useCrmApi();

  const [views, setViews] = useState<OrderSystemView[]>(INITIAL_VIEWS);
  const [active, setActive] = useState<Active>({ kind: 'system', key: 'all-orders' });
  const [filters, setFilters] = useState<OrderFilterClause[]>([]);
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [accountId, setAccountId] = useState('');
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [data, setData] = useState<OrderSearchResponse | null>(null);
  const [page, setPage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const requestSeq = useRef(0);

  // -------------------------------------------------------------- search
  const runSearch = useCallback(
    (req: OrderSearchRequest) => {
      const seq = ++requestSeq.current;
      setError(null);
      api
        .searchOrders({ ...req, limit: PAGE_SIZE })
        .then((next) => {
          if (seq === requestSeq.current) {
            setData(next);
            if (next.views.length) setViews(next.views);
          }
        })
        .catch((e: unknown) => {
          if (seq === requestSeq.current) {
            setError(e instanceof ApiError ? e.message : String(e));
          }
        });
    },
    [api],
  );

  const requestFor = useCallback(
    (
      next: Active,
      nextFilters: OrderFilterClause[],
      nextSearch: string,
      nextPage: number,
    ): OrderSearchRequest => {
      const offset = nextPage * PAGE_SIZE;
      const searchValue = nextSearch.trim() || null;
      if (next.kind === 'system') {
        return { system_view: next.key, search: searchValue, offset };
      }
      return { filters: nextFilters, search: searchValue, offset };
    },
    [],
  );

  const apply = useCallback(
    (next: Active, nextFilters: OrderFilterClause[], nextSearch: string, nextPage: number) => {
      setActive(next);
      setFilters(nextFilters);
      setPage(nextPage);
      runSearch(requestFor(next, nextFilters, nextSearch, nextPage));
    },
    [runSearch, requestFor],
  );

  useEffect(() => {
    crm
      .listAccounts()
      .then(setAccounts)
      .catch(() => undefined);
    runSearch(requestFor({ kind: 'system', key: 'all-orders' }, [], '', 0));
    // Run once on mount; subsequent loads go through the handlers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Build the adhoc filter set from the current toolbar controls (Date-Placed
   *  range + Account). Applying any of them turns off the active system view. */
  const buildFilters = useCallback(
    (from: string, to: string, account: string): OrderFilterClause[] => {
      const next: OrderFilterClause[] = [];
      if (from) next.push({ field: 'created_at', op: 'gte', value: `${from}T00:00:00` });
      // Include the whole final day: Postgres timestamps have microsecond
      // precision, so cap at 23:59:59.999999 (an order at 23:59:59.5 still matches).
      if (to) next.push({ field: 'created_at', op: 'lte', value: `${to}T23:59:59.999999` });
      if (account) next.push({ field: 'account_id', op: 'eq', value: account });
      return next;
    },
    [],
  );

  const selectView = (key: string) => {
    // A system view is a clean slate: clear the range/account filters (they can't
    // coexist with a system view server-side), but keep the free-text search.
    setDateFrom('');
    setDateTo('');
    setAccountId('');
    apply({ kind: 'system', key }, [], search, 0);
  };

  const applyToolbarFilters = (from: string, to: string, account: string) => {
    const next = buildFilters(from, to, account);
    // With no range/account filter, fall back to the All-Orders system view so the
    // default ordering is preserved; otherwise go adhoc.
    if (next.length === 0) apply({ kind: 'system', key: 'all-orders' }, [], search, 0);
    else apply({ kind: 'adhoc' }, next, search, 0);
  };

  const onSearchChange = (value: string) => {
    setSearch(value);
    apply(active, filters, value, 0);
  };

  const goToPage = (nextPage: number) => apply(active, filters, search, nextPage);

  const downloadPdf = (row: OrderRow) => {
    api
      .downloadOrderPdf(row.id)
      .then((blob) => saveBlob(blob, `Auftragsbestaetigung-${row.number}.pdf`))
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  };

  // -------------------------------------------------------------- the grid
  const numLocale = orderDateLocale(i18n.language);
  const fmtDate = (iso: string | null) => formatOrderDate(iso, numLocale);

  const columns = useMemo(
    () => [
      columnHelper.accessor('number', {
        header: () => t('orders.col.number'),
        cell: (info) => (
          <Link to={`/orders/${info.row.original.id}`}>{info.getValue()}</Link>
        ),
      }),
      columnHelper.accessor('quote_number', {
        header: () => t('orders.col.quote'),
        cell: (info) =>
          info.getValue() ? (
            <Link to={`/quotes/edit/${info.row.original.quote_id}`}>{info.getValue()}</Link>
          ) : (
            '—'
          ),
      }),
      columnHelper.accessor('account_name', {
        header: () => t('orders.col.account'),
        cell: (info) => info.getValue() ?? '—',
      }),
      columnHelper.accessor('contact_name', {
        header: () => t('orders.col.contact'),
        cell: (info) => info.getValue() ?? '—',
      }),
      columnHelper.accessor('po_number', {
        header: () => t('orders.col.po'),
        cell: (info) => info.getValue() ?? '—',
      }),
      columnHelper.accessor('created_at', {
        header: () => t('orders.col.date_placed'),
        cell: (info) => fmtDate(info.getValue()),
      }),
      columnHelper.accessor('parts_count', {
        header: () => t('orders.col.parts'),
        cell: (info) => info.getValue().toLocaleString(numLocale),
      }),
      columnHelper.display({
        id: 'total',
        header: () => t('orders.col.total'),
        // Order Total is NET (excl. VAT) — persisted minor units, German locale.
        cell: ({ row }) => (
          <span className="orders-num">
            {formatMinor(row.original.net_minor, row.original.currency)}
          </span>
        ),
      }),
      columnHelper.accessor('source', {
        header: () => t('orders.col.source'),
        cell: (info) => (
          <span className="crm-chip">{t(`orders.source.${info.getValue()}`)}</span>
        ),
      }),
      columnHelper.accessor('expected_ship_date', {
        header: () => t('orders.col.expected_ship'),
        cell: (info) => fmtDate(info.getValue()),
      }),
      columnHelper.display({
        id: 'actions',
        header: () => t('orders.col.actions'),
        cell: ({ row }) => (
          <details className="orders-menu">
            <summary aria-label={t('orders.actions.menu', { number: row.original.number })}>
              ⋮
            </summary>
            <menu className="orders-menu-list">
              <li>
                <Link to={`/orders/${row.original.id}`}>{t('orders.actions.view')}</Link>
              </li>
              {row.original.quote_number && (
                <li>
                  <Link to={`/quotes/edit/${row.original.quote_id}`}>
                    {t('orders.actions.open_quote')}
                  </Link>
                </li>
              )}
              {/* Edit order — gated (spec): shown only when the shop enabled
                  Facilitate Order Updates and the order has no shipment. The
                  editing drawer lands in M5.7; here it opens the detail view. */}
              {row.original.can_edit && (
                <li>
                  <Link to={`/orders/${row.original.id}?edit=1`}>
                    {t('orders.actions.edit')}
                  </Link>
                </li>
              )}
              <li>
                <button type="button" onClick={() => downloadPdf(row.original)}>
                  {t('orders.actions.download_pdf')}
                </button>
              </li>
            </menu>
          </details>
        ),
      }),
    ],
    // fmtDate/downloadPdf close over stable deps; re-memo on language only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t, i18n.language],
  );

  const table = useReactTable({
    data: data?.rows ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  const total = data?.total ?? 0;
  const offset = page * PAGE_SIZE;
  const title =
    active.kind === 'system'
      ? t(views.find((v) => v.key === active.key)?.label_key ?? 'orders.views.all')
      : t('orders.views.filtered');

  return (
    <section className="page orders-page">
      <div className="orders-main">
        <div className="crm-header">
          <h1 className="page-title">{title}</h1>
          {/* No CREATE ORDER button — orders come only from checkout / Build Order. */}
        </div>

        <nav className="orders-views" aria-label={t('orders.views_label')}>
          {views.map((v) => (
            <button
              key={v.key}
              type="button"
              className={
                'orders-view' +
                (active.kind === 'system' && active.key === v.key ? ' is-active' : '')
              }
              onClick={() => selectView(v.key)}
            >
              {t(v.label_key)}
            </button>
          ))}
        </nav>

        <div className="crm-toolbar orders-toolbar">
          <input
            className="crm-search"
            type="search"
            value={search}
            placeholder={t('orders.search_placeholder')}
            aria-label={t('orders.search_placeholder')}
            onChange={(e) => onSearchChange(e.target.value)}
          />
          <label className="orders-filter">
            <span>{t('orders.filter.date_from')}</span>
            <input
              type="date"
              className="crm-search"
              value={dateFrom}
              aria-label={t('orders.filter.date_from')}
              onChange={(e) => {
                setDateFrom(e.target.value);
                applyToolbarFilters(e.target.value, dateTo, accountId);
              }}
            />
          </label>
          <label className="orders-filter">
            <span>{t('orders.filter.date_to')}</span>
            <input
              type="date"
              className="crm-search"
              value={dateTo}
              aria-label={t('orders.filter.date_to')}
              onChange={(e) => {
                setDateTo(e.target.value);
                applyToolbarFilters(dateFrom, e.target.value, accountId);
              }}
            />
          </label>
          <label className="orders-filter">
            <span>{t('orders.filter.account')}</span>
            <select
              className="crm-search"
              value={accountId}
              aria-label={t('orders.filter.account')}
              onChange={(e) => {
                setAccountId(e.target.value);
                applyToolbarFilters(dateFrom, dateTo, e.target.value);
              }}
            >
              <option value="">{t('orders.filter.all_accounts')}</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        {error && (
          <p className="crm-error" role="alert">
            {error}
          </p>
        )}

        {total === 0 ? (
          <p className="page-empty">{t('orders.empty')}</p>
        ) : (
          <>
            <table className="crm-table orders-table">
              <thead>
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
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
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="quotes-footer">
              <span>
                {t('orders.footer', {
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
                  {t('orders.prev')}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => goToPage(page + 1)}
                >
                  {t('orders.next')}
                </button>
              </span>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
