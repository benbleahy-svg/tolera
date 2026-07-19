/**
 * The Outside-Services band on the Part Estimating view (M6.4, spec `#vendor-rfq`).
 *
 * Carries the second entry point into the batch-send modal ("Get Vendor Quote", with
 * this line pre-selected) and the spec's in-flight chip — "⏳ Awaiting N vendor
 * response(s)" — which disappears once every vendor has answered. In Buy mode it also
 * says so, because the internal costing below it is deliberately not driving the price.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { VendorRfqBatchModal } from './VendorRfqBatchModal';

export function OutsideServicesBand({
  quoteId,
  quoteItemId,
  awaitingResponses,
  costingMode,
  onSent,
  disabled = false,
}: {
  quoteId: string;
  quoteItemId: string;
  awaitingResponses: number;
  costingMode: 'make' | 'buy';
  onSent: () => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <section className="est-section" aria-label={t('vendorRfq.section.vendors')}>
      <div className="est-section-head">
        <h3>{t('estimating.outside_service')}</h3>
        {awaitingResponses > 0 && (
          <span className="est-chip est-chip-awaiting" role="status">
            {t('vendorRfq.awaiting', { count: awaitingResponses })}
          </span>
        )}
        {costingMode === 'buy' && (
          <span className="est-chip">{t('vendorRfq.costing_mode.buy')}</span>
        )}
        <button
          type="button"
          className="btn btn-secondary"
          disabled={disabled}
          onClick={() => setOpen(true)}
        >
          {t('vendorRfq.get_vendor_quote')}
        </button>
      </div>
      {open && (
        <VendorRfqBatchModal
          quoteId={quoteId}
          quoteItemIds={[quoteItemId]}
          onClose={() => setOpen(false)}
          onSent={() => {
            setOpen(false);
            onSent();
          }}
        />
      )}
    </section>
  );
}
