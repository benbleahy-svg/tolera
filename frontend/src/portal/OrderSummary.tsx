/**
 * Order-summary panel: the live NET subtotal of the buyer's selected
 * qty×lead-time rows and add-ons, with a "zzgl. MwSt." note (the portal shows
 * net only — VAT is computed server-side at checkout, M5.3). The "Proceed to
 * checkout" button (M5.2) is disabled without a selection or on a soft-expired
 * quote (portal reachable, checkout blocked — spec #digitalquote).
 */

import { useTranslation } from 'react-i18next';

import { formatMoney } from './money';

export function OrderSummary({
  subtotal,
  currency,
  hasSelection,
  isExpired,
  onCheckout,
}: {
  subtotal: string;
  currency: string;
  hasSelection: boolean;
  isExpired: boolean;
  onCheckout: () => void;
}) {
  const { t } = useTranslation();
  return (
    <aside className="portal-summary" aria-label={t('portal.order_summary')}>
      <h2>{t('portal.order_summary')}</h2>
      {hasSelection ? (
        <>
          <div className="portal-summary-row">
            <span>{t('portal.subtotal_net')}</span>
            <span className="portal-num">{formatMoney(subtotal, currency)}</span>
          </div>
          <p className="portal-vat-note">{t('portal.vat_note')}</p>
          <button
            type="button"
            className="portal-checkout-cta"
            onClick={onCheckout}
            disabled={isExpired}
          >
            {t('checkout.proceed')}
          </button>
          {isExpired && <p className="portal-vat-note">{t('checkout.expired_blocked')}</p>}
        </>
      ) : (
        <p className="portal-no-selection">{t('portal.no_selection')}</p>
      )}
    </aside>
  );
}
