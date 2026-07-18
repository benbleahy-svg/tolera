/**
 * Checkout flow (M5.2): the buyer completes a **PO-only** checkout for their
 * selected lines and places a real Order. Spec #digitalquote "Checkout flow (PO
 * only in v1)": Company & PO → Shipping → Review & Submit → Confirmation.
 *
 * The client sends IDs + quantities only — the server re-derives every price
 * and computes VAT (domestic / §13b reverse-charge / §19). VAT is therefore
 * authoritative from the confirmation payload, never invented here; the review
 * step shows the NET subtotal the portal already knows. German-first.
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { submitCheckout } from './api';
import { ApiError } from '../api/client';
import { formatMinor, formatMoney, sumMoney } from './money';
import type {
  BuyerAddOn,
  BuyerQuote,
  CheckoutLineSelection,
  CheckoutResult,
  LineSelection,
  ShippingMethod,
} from './types';

type SelectionMap = Map<string, LineSelection>;
type Step = 'company' | 'shipping' | 'review' | 'confirmation';

const SHIPPING_METHODS: ShippingMethod[] = [
  'bill_at_shipment',
  'use_my_shipping_account',
  'no_shipping_fees',
];

function addOnPriceFor(addOn: BuyerAddOn, quantity: number | null): string | null {
  const match = quantity != null ? addOn.prices.find((p) => p.quantity === quantity) : undefined;
  return (match ?? addOn.prices[0])?.price ?? null;
}

/** The NET total of one selected line (break/expedite + required + chosen add-ons). */
function lineNet(quote: BuyerQuote, quoteItemId: string, selection: LineSelection): string {
  const item = quote.line_items.find((i) => i.quote_item_id === quoteItemId);
  const brk = item?.breaks?.find((b) => b.quantity === selection.quantity);
  if (!item || !brk) return '0.0000';
  const parts: (string | null)[] = [];
  const exp = selection.expediteId
    ? brk.expedites.find((e) => e.id === selection.expediteId)
    : undefined;
  parts.push(exp?.total_price ?? brk.total_price);
  for (const addOn of item.add_ons ?? []) {
    if (addOn.is_required || selection.addOnIds.has(addOn.id)) {
      parts.push(addOnPriceFor(addOn, selection.quantity));
    }
  }
  return sumMoney(parts);
}

/** Build the checkout request from the client-side selection state. */
function toSelections(selections: SelectionMap): CheckoutLineSelection[] {
  const out: CheckoutLineSelection[] = [];
  for (const [quoteItemId, sel] of selections) {
    if (sel.quantity == null) continue;
    out.push({
      quote_item_id: quoteItemId,
      quantity: sel.quantity,
      expedite_option_id: sel.expediteId ?? undefined,
      add_on_ids: sel.addOnIds.size ? [...sel.addOnIds] : undefined,
    });
  }
  return out;
}

function lineLabel(quote: BuyerQuote, quoteItemId: string): string {
  const item = quote.line_items.find((i) => i.quote_item_id === quoteItemId);
  return item?.part_number || item?.description || `#${(item?.position ?? 0) + 1}`;
}

export function CheckoutFlow({
  quote,
  token,
  selections,
  subtotalNet,
  onClose,
  onComplete,
}: {
  quote: BuyerQuote;
  token: string;
  selections: SelectionMap;
  subtotalNet: string;
  onClose: () => void;
  /** Called from the confirmation's "Done" — distinct from a mid-flow cancel so
   *  the parent can clear the selection and stop a second order for it. */
  onComplete: () => void;
}) {
  const { t } = useTranslation();
  const { currency } = quote;
  const [step, setStep] = useState<Step>('company');
  const [poNumber, setPoNumber] = useState('');
  const [company, setCompany] = useState('');
  const [billing, setBilling] = useState('');
  const [ustId, setUstId] = useState('');
  const [notes, setNotes] = useState('');
  const [shipping, setShipping] = useState<ShippingMethod>('bill_at_shipment');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CheckoutResult | null>(null);

  const selectedLines = useMemo(
    () => [...selections.entries()].filter(([, s]) => s.quantity != null),
    [selections],
  );

  const canSubmit = poNumber.trim().length > 0 && selectedLines.length > 0;

  async function placeOrder() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await submitCheckout(token, {
        selections: toSelections(selections),
        po_number: poNumber.trim(),
        company_name: company.trim() || null,
        billing_address: billing.trim() || null,
        notes: notes.trim() || null,
        buyer_ust_id_nr: ustId.trim() || null,
        shipping_method: shipping,
      });
      setResult(res);
      setStep('confirmation');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('checkout.error_generic'));
    } finally {
      setSubmitting(false);
    }
  }

  // --- Confirmation ------------------------------------------------------- //
  if (step === 'confirmation' && result) {
    return (
      <section className="portal-checkout" aria-label={t('checkout.title')}>
        <div className="portal-checkout-confirmation" role="status">
          <h2>{t('checkout.confirmed_title')}</h2>
          <p className="portal-checkout-ordernum">
            {t('checkout.order_number', { number: result.order_number })}
          </p>
          <p>{t('checkout.confirmed_body', { shop: quote.shop.name })}</p>
          <dl className="portal-checkout-totals">
            <div>
              <dt>{t('checkout.net')}</dt>
              <dd className="portal-num">{formatMinor(result.net_minor, result.currency)}</dd>
            </div>
            {result.reverse_charge ? (
              <div>
                <dt>{t('checkout.reverse_charge')}</dt>
                <dd className="portal-num">{result.tax_note}</dd>
              </div>
            ) : result.kleinunternehmer ? (
              <div>
                <dt>{t('checkout.vat')}</dt>
                <dd className="portal-num">{result.tax_note}</dd>
              </div>
            ) : (
              <div>
                <dt>
                  {result.vat_label ?? t('checkout.vat')} ({result.vat_rate_pct} %)
                </dt>
                <dd className="portal-num">{formatMinor(result.vat_minor, result.currency)}</dd>
              </div>
            )}
            <div className="portal-checkout-gross">
              <dt>{t('checkout.gross')}</dt>
              <dd className="portal-num">{formatMinor(result.gross_minor, result.currency)}</dd>
            </div>
          </dl>
          <button type="button" className="portal-checkout-close" onClick={onComplete}>
            {t('checkout.done')}
          </button>
        </div>
      </section>
    );
  }

  // --- Wizard steps ------------------------------------------------------- //
  return (
    <section className="portal-checkout" aria-label={t('checkout.title')}>
      <header className="portal-checkout-header">
        <h2>{t('checkout.title')}</h2>
        <button type="button" className="portal-checkout-back" onClick={onClose}>
          {t('checkout.back_to_quote')}
        </button>
      </header>

      {error && (
        <p className="portal-checkout-error" role="alert">
          {error}
        </p>
      )}

      {step === 'company' && (
        <form
          className="portal-checkout-form"
          onSubmit={(e) => {
            e.preventDefault();
            setStep('shipping');
          }}
        >
          <label>
            {t('checkout.po_number')} *
            <input
              type="text"
              required
              value={poNumber}
              onChange={(e) => setPoNumber(e.target.value)}
            />
          </label>
          <label>
            {t('checkout.company')}
            <input type="text" value={company} onChange={(e) => setCompany(e.target.value)} />
          </label>
          <label>
            {t('checkout.billing_address')}
            <textarea value={billing} onChange={(e) => setBilling(e.target.value)} rows={3} />
          </label>
          <label>
            {t('checkout.ust_id')}
            <input
              type="text"
              value={ustId}
              onChange={(e) => setUstId(e.target.value)}
              placeholder="DE / ATU …"
            />
            <span className="portal-checkout-hint">{t('checkout.ust_id_hint')}</span>
          </label>
          <label>
            {t('checkout.notes')}
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
          </label>
          <button type="submit" disabled={!poNumber.trim()}>
            {t('checkout.continue')}
          </button>
        </form>
      )}

      {step === 'shipping' && (
        <div className="portal-checkout-shipping">
          <fieldset>
            <legend>{t('checkout.shipping')}</legend>
            {SHIPPING_METHODS.map((method) => (
              <label key={method} className="portal-checkout-shipping-option">
                <input
                  type="radio"
                  name="shipping-method"
                  value={method}
                  checked={shipping === method}
                  onChange={() => setShipping(method)}
                />
                {t(`checkout.shipping_${method}`)}
              </label>
            ))}
          </fieldset>
          <div className="portal-checkout-nav">
            <button type="button" onClick={() => setStep('company')}>
              {t('checkout.back')}
            </button>
            <button type="button" onClick={() => setStep('review')}>
              {t('checkout.continue')}
            </button>
          </div>
        </div>
      )}

      {step === 'review' && (
        <div className="portal-checkout-review">
          <h3>{t('checkout.review')}</h3>
          <ul className="portal-checkout-lines">
            {selectedLines.map(([quoteItemId, sel]) => (
              <li key={quoteItemId}>
                <span>
                  {lineLabel(quote, quoteItemId)} · {t('checkout.qty', { qty: sel.quantity })}
                </span>
                <span className="portal-num">
                  {formatMoney(lineNet(quote, quoteItemId, sel), currency)}
                </span>
              </li>
            ))}
          </ul>
          <dl className="portal-checkout-totals">
            <div>
              <dt>{t('portal.subtotal_net')}</dt>
              <dd className="portal-num">{formatMoney(subtotalNet, currency)}</dd>
            </div>
            <div>
              <dt>{t('checkout.po_number')}</dt>
              <dd>{poNumber}</dd>
            </div>
            <div>
              <dt>{t('checkout.shipping')}</dt>
              <dd>{t(`checkout.shipping_${shipping}`)}</dd>
            </div>
          </dl>
          <p className="portal-vat-note">{t('checkout.vat_computed_note')}</p>
          <div className="portal-checkout-nav">
            <button type="button" onClick={() => setStep('shipping')} disabled={submitting}>
              {t('checkout.back')}
            </button>
            <button
              type="button"
              className="portal-checkout-place"
              onClick={placeOrder}
              disabled={!canSubmit || submitting}
            >
              {submitting ? t('checkout.placing') : t('checkout.place_order')}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
