/**
 * Order detail — the `/orders/:orderId` view (spec #orderslist → order detail).
 * Header (Order #, source, PO, account/contact, dates), the persisted §14-UStG tax
 * breakdown (a read of the stored Order — never a recompute), and the ordered
 * lines. A Download-PDF button hits the M5.4 order-confirmation variant; an Edit
 * button appears only when the order is editable (Facilitate Order Updates on + no
 * shipment) — the editing drawer itself is M5.7, so here it is a disabled preview.
 *
 * No status lifecycle: the only shipment state is `shipped_at` (a "Shipped on …"
 * line when set), matching the ERP-owned model.
 */

import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { formatMinor } from '../portal/money';
import { formatOrderDate, orderDateLocale } from './dates';
import { useOrdersApi } from './api';
import type { OrderDetail } from './types';

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

export function OrderDetailPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const { t, i18n } = useTranslation();
  const api = useOrdersApi();

  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!orderId) return;
    // Clear the previous order/error so a slow fetch never shows a stale order
    // while navigating between details; ignore a response that resolves after the
    // orderId changed (cancelled) so it can't overwrite the current view.
    let active = true;
    setOrder(null);
    setError(null);
    api
      .getOrder(orderId)
      .then((next) => {
        if (active) setOrder(next);
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof ApiError ? e.message : String(e));
      });
    return () => {
      active = false;
    };
  }, [api, orderId]);

  const numLocale = orderDateLocale(i18n.language);
  const fmtDate = (iso: string | null) => formatOrderDate(iso, numLocale);

  const downloadPdf = () => {
    if (!order) return;
    api
      .downloadOrderPdf(order.id)
      .then((blob) => saveBlob(blob, `Auftragsbestaetigung-${order.number}.pdf`))
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  };

  if (error) {
    return (
      <section className="page orders-detail-page">
        <p className="crm-error" role="alert">
          {error}
        </p>
        <Link to="/orders">{t('orders.detail.back')}</Link>
      </section>
    );
  }

  if (!order) {
    return (
      <section className="page orders-detail-page">
        <p className="page-empty">{t('orders.detail.loading')}</p>
      </section>
    );
  }

  const money = (minor: number) => formatMinor(minor, order.currency);

  return (
    <section className="page orders-detail-page">
      <div className="crm-header">
        <div>
          <Link to="/orders" className="orders-detail-back">
            ← {t('orders.detail.back')}
          </Link>
          <h1 className="page-title">
            {t('orders.detail.title', { number: order.number })}
            <span className="crm-chip orders-detail-source">
              {t(`orders.source.${order.source}`)}
            </span>
          </h1>
        </div>
        <div className="orders-detail-actions">
          <button type="button" className="btn btn-ghost" onClick={downloadPdf}>
            {t('orders.actions.download_pdf')}
          </button>
          {order.can_edit && (
            <button
              type="button"
              className="btn btn-primary"
              disabled
              title={t('orders.detail.edit_soon')}
            >
              {t('orders.actions.edit')}
            </button>
          )}
        </div>
      </div>

      <dl className="orders-detail-grid">
        <div>
          <dt>{t('orders.col.quote')}</dt>
          <dd>
            {order.quote_number ? (
              <Link to={`/quotes/edit/${order.quote_id}`}>{order.quote_number}</Link>
            ) : (
              '—'
            )}
          </dd>
        </div>
        <div>
          <dt>{t('orders.col.account')}</dt>
          <dd>{order.account_name ?? order.company_name ?? '—'}</dd>
        </div>
        <div>
          <dt>{t('orders.col.contact')}</dt>
          <dd>{order.contact_name ?? '—'}</dd>
        </div>
        <div>
          <dt>{t('orders.col.po')}</dt>
          <dd>{order.po_number ?? '—'}</dd>
        </div>
        <div>
          <dt>{t('orders.col.date_placed')}</dt>
          <dd>{fmtDate(order.created_at)}</dd>
        </div>
        <div>
          <dt>{t('orders.col.expected_ship')}</dt>
          <dd>{fmtDate(order.expected_ship_date)}</dd>
        </div>
        {order.shipped_at && (
          <div>
            <dt>{t('orders.detail.shipped_at')}</dt>
            <dd>{fmtDate(order.shipped_at)}</dd>
          </div>
        )}
        {order.billing_address && (
          <div>
            <dt>{t('orders.detail.billing_address')}</dt>
            <dd className="orders-detail-address">{order.billing_address}</dd>
          </div>
        )}
      </dl>

      <h2 className="orders-detail-subtitle">{t('orders.detail.lines')}</h2>
      <table className="crm-table orders-detail-lines">
        <thead>
          <tr>
            <th>{t('orders.detail.line_part')}</th>
            <th>{t('orders.detail.line_qty')}</th>
            <th>{t('orders.detail.line_ships_on')}</th>
            <th>{t('orders.detail.line_unit')}</th>
            <th>{t('orders.detail.line_total')}</th>
          </tr>
        </thead>
        <tbody>
          {order.lines.map((ln) => (
            <tr key={ln.id}>
              {/* Identify the ordered part; fall back to the line position. */}
              <td>{ln.part_label ?? t('orders.detail.line_position', { position: ln.position })}</td>
              <td>{ln.quantity.toLocaleString(numLocale)}</td>
              <td>{fmtDate(ln.ships_on)}</td>
              <td className="orders-num">{money(ln.unit_price_minor)}</td>
              <td className="orders-num">{money(ln.total_price_minor)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <dl className="orders-detail-totals">
        <div>
          <dt>{t('orders.detail.net')}</dt>
          <dd className="orders-num">{money(order.net_minor)}</dd>
        </div>
        {order.reverse_charge ? (
          <div className="orders-detail-note">
            <dd>{order.tax_note ?? t('orders.detail.reverse_charge')}</dd>
          </div>
        ) : order.kleinunternehmer ? (
          <div className="orders-detail-note">
            <dd>{order.tax_note ?? t('orders.detail.kleinunternehmer')}</dd>
          </div>
        ) : order.tax_rate_lines && order.tax_rate_lines.length > 0 ? (
          // Render the persisted per-rate §14 breakdown (a mixed-rate order carries
          // e.g. 19% + 7%); one aggregate line would misstate it. Read-only — the
          // figures are the stored breakdown, never recomputed here.
          order.tax_rate_lines.map((line) => (
            <div key={line.rate_pct}>
              <dt>{t('orders.detail.vat', { rate: line.rate_pct.toLocaleString(numLocale) })}</dt>
              <dd className="orders-num">{money(line.vat_minor)}</dd>
            </div>
          ))
        ) : (
          <div>
            <dt>
              {t('orders.detail.vat', {
                rate: order.vat_rate_pct.toLocaleString(numLocale),
              })}
            </dt>
            <dd className="orders-num">{money(order.vat_minor)}</dd>
          </div>
        )}
        <div className="orders-detail-gross">
          <dt>{t('orders.detail.gross')}</dt>
          <dd className="orders-num">{money(order.gross_minor)}</dd>
        </div>
      </dl>
    </section>
  );
}
