/**
 * Build Order (Facilitate Order) drawer (M5.7, spec #order Step 1 + Step 2;
 * screenshot DemoH/12). Two steps:
 *
 *  1. Build Order — per line item choose ONE quantity break (radio: Qty, Lead
 *     Time, Ships On, Unit Price, Total Price), add per-line Discounts (Percent)
 *     and Additional Charges (Price), and adjust Ships-On (per line or bulk
 *     "EDIT SHIPS ON"). A line can be dropped from the order.
 *  2. Shipping & Payment — payment method (Not Provided / Purchase Order — credit
 *     card is hidden in v1), shipping method, billing address.
 *
 * Purely presentational: priced breaks come in as `lines`, and REVIEW ORDER emits
 * a `FacilitateOrderRequest` for the caller to POST. Money is integer minor units;
 * the shop-entered discount percent / charge amount are the only free money inputs.
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { formatMinor } from '../portal/money';
import type {
  FacilitateCharge,
  FacilitateDiscount,
  FacilitateLineSelection,
  FacilitateOrderRequest,
  OrderShippingMethod,
} from './types';

/** One priced quantity break offered for a line item. */
export interface FacilitateBreak {
  quantity: number;
  lead_time_days: number | null;
  unit_price_minor: number;
  total_price_minor: number;
}

/** A quote line item with its priced breaks, ready to build into an order. */
export interface FacilitatePricedLine {
  quote_item_id: string;
  part_label: string;
  breaks: FacilitateBreak[];
}

const SHIPPING_METHODS: OrderShippingMethod[] = [
  'bill_at_shipment',
  'use_my_shipping_account',
  'no_shipping_fees',
];

interface LineState {
  included: boolean;
  breakIndex: number;
  shipsOn: string;
  discounts: FacilitateDiscount[];
  charges: FacilitateCharge[];
}

interface FacilitateOrderDrawerProps {
  lines: FacilitatePricedLine[];
  currency: string;
  /** Placement date (ISO) — the Ships-On default base = this + the break lead time. */
  placedOn: string;
  submitting?: boolean;
  onSubmit: (req: FacilitateOrderRequest) => void;
  onClose: () => void;
}

function addDays(iso: string, days: number | null): string {
  if (days == null) return iso;
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** The discounted-then-charged line total in minor units (mirrors the backend:
 *  each discount rounds on the break total; charges add). */
function lineTotalMinor(brk: FacilitateBreak, st: LineState): number {
  let total = brk.total_price_minor;
  for (const d of st.discounts) {
    const pct = Number(d.percent) || 0;
    total -= Math.round((brk.total_price_minor * pct) / 100);
  }
  for (const c of st.charges) {
    total += Math.round((Number(c.amount) || 0) * 100);
  }
  return total;
}

export function FacilitateOrderDrawer({
  lines,
  currency,
  placedOn,
  submitting = false,
  onSubmit,
  onClose,
}: FacilitateOrderDrawerProps) {
  const { t, i18n } = useTranslation();
  const locale = currency === 'CHF' ? 'de-CH' : i18n.language === 'de' ? 'de-DE' : 'en-IE';
  const money = (minor: number) => formatMinor(minor, currency);

  const [step, setStep] = useState<1 | 2>(1);
  const [search, setSearch] = useState('');
  const [bulkShipsOn, setBulkShipsOn] = useState('');
  const [payment, setPayment] = useState<'not_provided' | 'purchase_order'>('not_provided');
  const [poNumber, setPoNumber] = useState('');
  const [shipping, setShipping] = useState<'' | OrderShippingMethod>('');
  const [billing, setBilling] = useState('');

  const [state, setState] = useState<Record<string, LineState>>(() =>
    Object.fromEntries(
      lines.map((ln) => [
        ln.quote_item_id,
        {
          included: true,
          breakIndex: 0,
          shipsOn: addDays(placedOn, ln.breaks[0]?.lead_time_days ?? null),
          discounts: [],
          charges: [],
        } satisfies LineState,
      ]),
    ),
  );

  const update = (id: string, patch: Partial<LineState>) =>
    setState((s) => ({ ...s, [id]: { ...s[id], ...patch } }));

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? lines.filter((ln) => ln.part_label.toLowerCase().includes(q)) : lines;
  }, [lines, search]);

  const included = lines.filter((ln) => state[ln.quote_item_id]?.included);
  const subtotal = included.reduce((sum, ln) => {
    const st = state[ln.quote_item_id];
    const brk = ln.breaks[st.breakIndex];
    return brk ? sum + lineTotalMinor(brk, st) : sum;
  }, 0);

  function chooseBreak(ln: FacilitatePricedLine, idx: number) {
    update(ln.quote_item_id, {
      breakIndex: idx,
      shipsOn: addDays(placedOn, ln.breaks[idx]?.lead_time_days ?? null),
    });
  }

  function applyBulkShipsOn() {
    if (!bulkShipsOn) return;
    setState((s) => {
      const next = { ...s };
      for (const ln of included) next[ln.quote_item_id] = { ...s[ln.quote_item_id], shipsOn: bulkShipsOn };
      return next;
    });
  }

  function buildRequest(): FacilitateOrderRequest {
    const selections: FacilitateLineSelection[] = included.map((ln) => {
      const st = state[ln.quote_item_id];
      const brk = ln.breaks[st.breakIndex];
      return {
        quote_item_id: ln.quote_item_id,
        quantity: brk.quantity,
        ships_on: st.shipsOn || null,
        discounts: st.discounts.filter((d) => d.label.trim() && Number(d.percent) > 0),
        additional_charges: st.charges.filter((c) => c.label.trim() && Number(c.amount) > 0),
      };
    });
    return {
      selections,
      po_number: payment === 'purchase_order' ? poNumber.trim() || null : null,
      billing_address: billing.trim() || null,
      shipping_method: shipping || null,
    };
  }

  return (
    <div className="orders-build-drawer" role="dialog" aria-modal="true" aria-label={t('orders.build.title')}>
      <div className="orders-build-panel">
        <header className="orders-build-header">
          <h2>{step === 1 ? t('orders.build.title') : t('orders.build.step2_title')}</h2>
          <button type="button" className="orders-edit-close" aria-label={t('orders.edit.cancel')} onClick={onClose}>
            ×
          </button>
        </header>

        {step === 1 ? (
          <>
            <div className="orders-build-toolbar">
              <span className="orders-build-count">
                {t('orders.build.selected', { n: included.length, total: lines.length })}
              </span>
              <label className="orders-build-bulk">
                {t('orders.build.edit_ships_on')}
                <input
                  type="date"
                  value={bulkShipsOn}
                  onChange={(e) => setBulkShipsOn(e.target.value)}
                  onBlur={applyBulkShipsOn}
                  aria-label={t('orders.build.edit_ships_on')}
                />
              </label>
              <input
                className="orders-build-search"
                type="search"
                placeholder={t('orders.build.search_placeholder')}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            {visible.map((ln, i) => {
              const st = state[ln.quote_item_id];
              if (!st) return null;
              return (
                <article
                  key={ln.quote_item_id}
                  className={`orders-build-card${st.included ? '' : ' is-excluded'}`}
                >
                  <div className="orders-build-card-head">
                    <span className="orders-build-idx">{i + 1}</span>
                    <span className="orders-build-part">{ln.part_label}</span>
                    <button
                      type="button"
                      className="orders-edit-close"
                      aria-label={t('orders.build.remove_line')}
                      onClick={() => update(ln.quote_item_id, { included: !st.included })}
                    >
                      ×
                    </button>
                  </div>

                  <table className="orders-build-breaks">
                    <thead>
                      <tr>
                        <th />
                        <th>{t('orders.build.col_qty')}</th>
                        <th>{t('orders.build.col_lead')}</th>
                        <th>{t('orders.build.col_ships_on')}</th>
                        <th>{t('orders.build.col_unit')}</th>
                        <th>{t('orders.build.col_total')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ln.breaks.map((brk, bi) => (
                        <tr key={brk.quantity}>
                          <td>
                            <input
                              type="radio"
                              name={`brk-${ln.quote_item_id}`}
                              checked={st.breakIndex === bi}
                              disabled={!st.included}
                              aria-label={t('orders.build.col_qty') + ' ' + brk.quantity}
                              onChange={() => chooseBreak(ln, bi)}
                            />
                          </td>
                          <td>{brk.quantity.toLocaleString(locale)}</td>
                          <td>
                            {brk.lead_time_days == null
                              ? '—'
                              : t('orders.build.lead_days', { n: brk.lead_time_days })}
                          </td>
                          <td>
                            {st.breakIndex === bi ? (
                              <input
                                type="date"
                                value={st.shipsOn}
                                disabled={!st.included}
                                aria-label={t('orders.build.col_ships_on')}
                                onChange={(e) => update(ln.quote_item_id, { shipsOn: e.target.value })}
                              />
                            ) : (
                              addDays(placedOn, brk.lead_time_days)
                            )}
                          </td>
                          <td className="orders-num">{money(brk.unit_price_minor)}</td>
                          <td className="orders-num">{money(brk.total_price_minor)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  <AdjustmentsEditor
                    heading={t('orders.build.discounts')}
                    valueLabel={t('orders.build.percent')}
                    addLabel={t('orders.build.add_adjustment')}
                    labelPlaceholder={t('orders.build.adjustment_label')}
                    rows={st.discounts.map((d) => ({ label: d.label, value: d.percent }))}
                    disabled={!st.included}
                    onChange={(rows) =>
                      update(ln.quote_item_id, {
                        discounts: rows.map((r) => ({ label: r.label, percent: r.value })),
                      })
                    }
                  />
                  <AdjustmentsEditor
                    heading={t('orders.build.additional_charges')}
                    valueLabel={t('orders.build.price')}
                    addLabel={t('orders.build.add_charge')}
                    labelPlaceholder={t('orders.build.adjustment_label')}
                    rows={st.charges.map((c) => ({ label: c.label, value: c.amount }))}
                    disabled={!st.included}
                    onChange={(rows) =>
                      update(ln.quote_item_id, {
                        charges: rows.map((r) => ({ label: r.label, amount: r.value })),
                      })
                    }
                  />
                </article>
              );
            })}

            <footer className="orders-build-footer">
              <span>{t('orders.build.parts_in_order', { n: included.length })}</span>
              <span className="orders-num">{money(subtotal)}</span>
              <button
                type="button"
                className="btn btn-primary"
                disabled={included.length === 0}
                onClick={() => setStep(2)}
              >
                {t('orders.build.continue')}
              </button>
            </footer>
          </>
        ) : (
          <form
            className="orders-edit-form"
            onSubmit={(e) => {
              e.preventDefault();
              onSubmit(buildRequest());
            }}
          >
            <fieldset className="orders-build-payment">
              <legend>{t('orders.build.payment_method')}</legend>
              <label className="orders-edit-notify">
                <input
                  type="radio"
                  name="payment"
                  checked={payment === 'not_provided'}
                  onChange={() => setPayment('not_provided')}
                />
                {t('orders.build.payment_not_provided')}
              </label>
              <label className="orders-edit-notify">
                <input
                  type="radio"
                  name="payment"
                  checked={payment === 'purchase_order'}
                  onChange={() => setPayment('purchase_order')}
                />
                {t('orders.build.payment_po')}
              </label>
            </fieldset>
            {payment === 'purchase_order' && (
              <label>
                {t('orders.build.po_number')}
                <input value={poNumber} onChange={(e) => setPoNumber(e.target.value)} />
              </label>
            )}
            <label>
              {t('orders.build.shipping_method')}
              <select value={shipping} onChange={(e) => setShipping(e.target.value as '' | OrderShippingMethod)}>
                <option value="">{t('orders.shipping.none')}</option>
                {SHIPPING_METHODS.map((m) => (
                  <option key={m} value={m}>
                    {t(`orders.shipping.${m}`)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t('orders.build.billing_address')}
              <textarea value={billing} rows={3} onChange={(e) => setBilling(e.target.value)} />
            </label>

            <div className="orders-edit-actions">
              <button type="button" className="btn btn-ghost" onClick={() => setStep(1)}>
                {t('orders.build.go_back')}
              </button>
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? t('orders.build.creating') : t('orders.build.review_order')}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// A small repeatable label+value editor for Discounts / Additional Charges.
// --------------------------------------------------------------------------- //
interface AdjRow {
  label: string;
  value: string;
}

function AdjustmentsEditor(props: {
  heading: string;
  valueLabel: string;
  addLabel: string;
  labelPlaceholder: string;
  rows: AdjRow[];
  disabled: boolean;
  onChange: (rows: AdjRow[]) => void;
}) {
  const { heading, valueLabel, addLabel, labelPlaceholder, rows, disabled, onChange } = props;
  return (
    <div className="orders-build-adj">
      <div className="orders-build-adj-head">
        <span>{heading}</span>
        <span>{valueLabel}</span>
      </div>
      {rows.map((row, i) => (
        <div className="orders-build-adj-row" key={i}>
          <input
            value={row.label}
            placeholder={labelPlaceholder}
            disabled={disabled}
            onChange={(e) => onChange(rows.map((r, j) => (j === i ? { ...r, label: e.target.value } : r)))}
          />
          <input
            type="number"
            min="0"
            step="0.01"
            value={row.value}
            disabled={disabled}
            aria-label={valueLabel}
            onChange={(e) => onChange(rows.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)))}
          />
          <button
            type="button"
            className="orders-edit-close"
            aria-label="×"
            disabled={disabled}
            onClick={() => onChange(rows.filter((_, j) => j !== i))}
          >
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        className="orders-build-add"
        disabled={disabled}
        onClick={() => onChange([...rows, { label: '', value: '' }])}
      >
        + {addLabel}
      </button>
    </div>
  );
}
