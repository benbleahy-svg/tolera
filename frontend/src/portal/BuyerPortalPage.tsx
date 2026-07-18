/**
 * Buyer-portal page (M5.1): the PUBLIC, unauthenticated, white-label read-only
 * Digital Quote at `/q/:token`. Fetches the quote on mount, holds per-line
 * selection state client-side (M5.2 checkout consumes it — no place-order here),
 * and renders the shop header, quote-header strip (with a soft-expiry EXPIRED
 * badge), the available-from range chip, the line-item cards, and a live NET
 * order-summary. Soft expiry: selection stays ENABLED even when expired.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { fetchBuyerQuote } from './api';
import { CheckoutFlow } from './CheckoutFlow';
import { LineItemCard } from './LineItemCard';
import { sumMoney } from './money';
import { OrderSummary } from './OrderSummary';
import { RangeChip } from './RangeChip';
import type { BuyerAddOn, BuyerQuote, LineSelection } from './types';

type SelectionMap = Map<string, LineSelection>;

/** The add-on's price at the selected quantity, falling back to its first tier. */
function addOnPriceFor(addOn: BuyerAddOn, quantity: number | null): string | null {
  const match = quantity != null ? addOn.prices.find((p) => p.quantity === quantity) : undefined;
  return (match ?? addOn.prices[0])?.price ?? null;
}

/** Sum the NET contribution of every selected line (break/expedite + add-ons). */
function computeSubtotal(quote: BuyerQuote, selections: SelectionMap): string {
  const parts: (string | null)[] = [];
  for (const item of quote.line_items) {
    const selection = selections.get(item.quote_item_id);
    if (!selection || selection.quantity == null) continue;
    const brk = item.breaks?.find((b) => b.quantity === selection.quantity);
    if (!brk) continue;
    if (selection.expediteId) {
      const exp = brk.expedites.find((e) => e.id === selection.expediteId);
      parts.push(exp?.total_price ?? brk.total_price);
    } else {
      parts.push(brk.total_price);
    }
    for (const addOn of item.add_ons ?? []) {
      if (addOn.is_required || selection.addOnIds.has(addOn.id)) {
        parts.push(addOnPriceFor(addOn, selection.quantity));
      }
    }
  }
  return sumMoney(parts);
}

function formatDate(iso: string, locale: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(locale, { dateStyle: 'long' }).format(date);
}

export function BuyerPortalPage() {
  const { t } = useTranslation();
  const { token } = useParams<{ token: string }>();
  const [quote, setQuote] = useState<BuyerQuote | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [selections, setSelections] = useState<SelectionMap>(new Map());
  const [checkingOut, setCheckingOut] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setFailed(false);
    // Reset per-quote state when the token changes so a prior quote's selection
    // can't bleed into the new one (overlapping line-item ids / stale subtotal).
    setQuote(null);
    setSelections(new Map());
    setCheckingOut(false);
    if (!token) {
      setFailed(true);
      setLoading(false);
      return;
    }
    fetchBuyerQuote(token)
      .then((data) => {
        if (!active) return;
        setQuote(data);
        setLoading(false);
      })
      .catch(() => {
        if (!active) return;
        setFailed(true);
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token]);

  const updateSelection = (quoteItemId: string, patch: Partial<LineSelection>) => {
    setSelections((prev) => {
      const next = new Map(prev);
      const current = next.get(quoteItemId) ?? {
        quantity: null,
        expediteId: null,
        addOnIds: new Set<string>(),
      };
      next.set(quoteItemId, { ...current, ...patch });
      return next;
    });
  };

  const toggleAddOn = (quoteItemId: string, addOnId: string) => {
    setSelections((prev) => {
      const next = new Map(prev);
      const current = next.get(quoteItemId) ?? {
        quantity: null,
        expediteId: null,
        addOnIds: new Set<string>(),
      };
      const addOnIds = new Set(current.addOnIds);
      if (addOnIds.has(addOnId)) addOnIds.delete(addOnId);
      else addOnIds.add(addOnId);
      next.set(quoteItemId, { ...current, addOnIds });
      return next;
    });
  };

  const subtotal = useMemo(
    () => (quote ? computeSubtotal(quote, selections) : '0.0000'),
    [quote, selections],
  );
  const hasSelection = useMemo(
    () => [...selections.values()].some((s) => s.quantity != null),
    [selections],
  );

  if (loading) {
    return (
      <div className="portal-state" role="status">
        <div className="portal-spinner" aria-hidden="true" />
        <p>{t('portal.loading')}</p>
      </div>
    );
  }

  if (failed || !quote) {
    return (
      <div className="portal-state portal-error" role="alert">
        <p>{t('portal.invalid_link')}</p>
      </div>
    );
  }

  const locale = quote.currency === 'CHF' ? 'de-CH' : 'de-DE';

  if (checkingOut && token) {
    return (
      <div className="portal-root">
        <header className="portal-shop-header">
          <h1 className="portal-shop-name">{quote.shop.name}</h1>
        </header>
        <CheckoutFlow
          quote={quote}
          token={token}
          selections={selections}
          subtotalNet={subtotal}
          onClose={() => setCheckingOut(false)}
        />
      </div>
    );
  }

  return (
    <div className="portal-root">
      <header className="portal-shop-header">
        <h1 className="portal-shop-name">{quote.shop.name}</h1>
      </header>

      <div className="portal-quote-strip">
        <span className="portal-quote-number">
          {t('portal.quote_number', { number: quote.quote_number })}
        </span>
        {quote.rfq_number && (
          <span className="portal-rfq-number">
            {t('portal.rfq_number', { number: quote.rfq_number })}
          </span>
        )}
        {quote.expiration_date && (
          <span className="portal-expiration">
            {t('portal.valid_until', { date: formatDate(quote.expiration_date, locale) })}
          </span>
        )}
        {quote.is_expired && <span className="portal-expired-badge">{t('portal.expired')}</span>}
        {quote.price_range && (
          <RangeChip
            min={quote.price_range.min_unit}
            max={quote.price_range.max_unit}
            currency={quote.currency}
          />
        )}
      </div>

      {quote.is_expired && (
        <div className="portal-expired-note" role="note">
          <p>{t('portal.expired_note')}</p>
          {quote.requotes_enabled && (
            <button type="button" className="portal-requote-btn">
              {t('portal.request_requote')}
            </button>
          )}
        </div>
      )}

      <main className="portal-body">
        <div className="portal-lines">
          {quote.line_items.map((item) => (
            <LineItemCard
              key={item.quote_item_id}
              item={item}
              currency={quote.currency}
              selection={selections.get(item.quote_item_id)}
              onSelectBreak={(quantity, expediteId) =>
                updateSelection(item.quote_item_id, { quantity, expediteId })
              }
              onToggleAddOn={(addOnId) => toggleAddOn(item.quote_item_id, addOnId)}
            />
          ))}
        </div>
        <OrderSummary
          subtotal={subtotal}
          currency={quote.currency}
          hasSelection={hasSelection}
          isExpired={quote.is_expired}
          onCheckout={() => setCheckingOut(true)}
        />
      </main>
    </div>
  );
}
