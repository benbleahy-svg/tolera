/**
 * Edit Order drawer (M5.7, spec #order "order editing" opt-in). A pre-shipment
 * edit of a facilitated/portal order — change PO number, company, billing address,
 * shipping method and notes, optionally notifying the buyer. Every save records an
 * entry in the order-history trail (shown below the form). Only fields the estimator
 * actually changed are sent (a partial PATCH), so an untouched order is a no-op.
 *
 * Opened from the OrderDetailPage Edit button, which is itself gated on the backend
 * `can_edit` (Facilitate Order Updates enabled + no shipment). The backend enforces
 * the same gate, returning 409 `order_not_editable` if it changed underneath us.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { formatOrderDate, orderDateLocale } from './dates';
import { useOrdersApi } from './api';
import type {
  OrderDetail,
  OrderEditRequest,
  OrderHistoryEvent,
  OrderShippingMethod,
} from './types';

const SHIPPING_METHODS: OrderShippingMethod[] = [
  'bill_at_shipment',
  'use_my_shipping_account',
  'no_shipping_fees',
];

interface EditOrderDrawerProps {
  order: OrderDetail;
  onClose: () => void;
  /** Called after a successful save so the detail view refetches. */
  onSaved: () => void;
}

export function EditOrderDrawer({ order, onClose, onSaved }: EditOrderDrawerProps) {
  const { t, i18n } = useTranslation();
  const api = useOrdersApi();

  const [poNumber, setPoNumber] = useState(order.po_number ?? '');
  const [company, setCompany] = useState(order.company_name ?? '');
  const [billing, setBilling] = useState(order.billing_address ?? '');
  const [shipping, setShipping] = useState<'' | OrderShippingMethod>(
    order.shipping_method ?? '',
  );
  const [notes, setNotes] = useState(order.notes ?? '');
  const [notifyBuyer, setNotifyBuyer] = useState(false);

  const [history, setHistory] = useState<OrderHistoryEvent[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api
      .getOrderHistory(order.id)
      .then((events) => {
        if (active) setHistory(events);
      })
      .catch(() => {
        /* history is auxiliary — a fetch failure must not block editing */
      });
    return () => {
      active = false;
    };
  }, [api, order.id]);

  const numLocale = orderDateLocale(i18n.language);

  /** The partial PATCH: only fields whose value differs from the loaded order. */
  function buildEdit(): OrderEditRequest {
    const req: OrderEditRequest = {};
    const trimmedPo = poNumber.trim();
    if (trimmedPo !== (order.po_number ?? '')) req.po_number = trimmedPo || null;
    if (company.trim() !== (order.company_name ?? '')) req.company_name = company.trim() || null;
    if (billing !== (order.billing_address ?? '')) req.billing_address = billing || null;
    if (notes !== (order.notes ?? '')) req.notes = notes || null;
    if (shipping !== (order.shipping_method ?? '')) {
      if (shipping === '') req.clear_shipping_method = true;
      else req.shipping_method = shipping;
    }
    if (notifyBuyer) req.notify_buyer = true;
    return req;
  }

  function handleSave() {
    const req = buildEdit();
    // Nothing changed (and no notify) → don't write an empty history entry.
    const hasFieldChange = Object.keys(req).some((k) => k !== 'notify_buyer');
    if (!hasFieldChange) {
      setError(t('orders.edit.no_changes'));
      return;
    }
    setSaving(true);
    setError(null);
    api
      .editOrder(order.id, req)
      .then(() => onSaved())
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.message : String(e));
        setSaving(false);
      });
  }

  return (
    <div className="orders-edit-drawer" role="dialog" aria-modal="true" aria-label={t('orders.edit.title')}>
      <div className="orders-edit-panel">
        <header className="orders-edit-header">
          <h2>{t('orders.edit.title')}</h2>
          <button type="button" className="orders-edit-close" aria-label={t('orders.edit.cancel')} onClick={onClose}>
            ×
          </button>
        </header>
        <p className="orders-edit-intro">{t('orders.edit.intro')}</p>

        {error && (
          <p className="crm-error" role="alert">
            {error}
          </p>
        )}

        <form
          className="orders-edit-form"
          onSubmit={(e) => {
            e.preventDefault();
            handleSave();
          }}
        >
          <label>
            {t('orders.edit.po_number')}
            <input value={poNumber} onChange={(e) => setPoNumber(e.target.value)} />
          </label>
          <label>
            {t('orders.edit.company')}
            <input value={company} onChange={(e) => setCompany(e.target.value)} />
          </label>
          <label>
            {t('orders.edit.billing_address')}
            <textarea value={billing} rows={3} onChange={(e) => setBilling(e.target.value)} />
          </label>
          <label>
            {t('orders.edit.shipping_method')}
            <select
              value={shipping}
              onChange={(e) => setShipping(e.target.value as '' | OrderShippingMethod)}
            >
              <option value="">{t('orders.shipping.none')}</option>
              {SHIPPING_METHODS.map((m) => (
                <option key={m} value={m}>
                  {t(`orders.shipping.${m}`)}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('orders.edit.notes')}
            <textarea value={notes} rows={2} onChange={(e) => setNotes(e.target.value)} />
          </label>
          <label className="orders-edit-notify">
            <input
              type="checkbox"
              checked={notifyBuyer}
              onChange={(e) => setNotifyBuyer(e.target.checked)}
            />
            {t('orders.edit.notify_buyer')}
          </label>

          <div className="orders-edit-actions">
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              {t('orders.edit.cancel')}
            </button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? t('orders.edit.saving') : t('orders.edit.save')}
            </button>
          </div>
        </form>

        <section className="orders-history">
          <h3>{t('orders.history.title')}</h3>
          {history.length === 0 ? (
            <p className="page-empty">{t('orders.history.empty')}</p>
          ) : (
            <ol className="orders-history-list">
              {history.map((ev) => (
                <li key={ev.id}>
                  <span className="orders-history-when">
                    {formatOrderDate(ev.created_at, numLocale)}
                  </span>
                  <span className="orders-history-what">{t(`orders.history.${ev.kind}`)}</span>
                  {ev.buyer_notified && (
                    <span className="crm-chip">{t('orders.history.notified')}</span>
                  )}
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </div>
  );
}
