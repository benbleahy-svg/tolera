/**
 * Order-summary panel (M5.1): the live NET subtotal of the buyer's selected
 * qty×lead-time rows and add-ons, with a "zzgl. MwSt." note (the portal shows
 * net only — no VAT math here). No checkout button: M5.2 owns place-order.
 */

import { useTranslation } from 'react-i18next';

import { formatMoney } from './money';

export function OrderSummary({
  subtotal,
  currency,
  hasSelection,
}: {
  subtotal: string;
  currency: string;
  hasSelection: boolean;
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
        </>
      ) : (
        <p className="portal-no-selection">{t('portal.no_selection')}</p>
      )}
    </aside>
  );
}
