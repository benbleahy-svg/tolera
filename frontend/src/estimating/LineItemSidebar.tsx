/**
 * Left line-item sidebar for the estimating screen (M5.0, spec #partview / DemoB 08):
 * the quote header, a selectable list of line items (with a priority badge), and the
 * "add line item" affordance. Selecting an item navigates to its spec route.
 *
 * M6.4 adds the spec's first Vendor-RFQ entry point: this list *is* this build's Quote
 * Detail line-item list, so the "check one or more line items → Send Vendor RFQ"
 * toolbar lives here. It opens the same modal the Outside-Services band does — the two
 * entry points differ only in what they pre-select. Each row also carries the
 * "⏳ Awaiting N vendor response(s)" chip, so an in-flight RFQ is visible without
 * opening the line.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { VendorRfqBatchModal } from '../vendor-rfq/VendorRfqBatchModal';
import type { QuoteSummary } from './types';

interface LineItemSidebarProps {
  quote: QuoteSummary;
  activeItemId: string | null;
  editable: boolean;
  onSelect: (itemId: string) => void;
  onAddItem: () => void;
  /** Refetch after a batch send so the awaiting chips are current (M6.4). */
  onVendorRfqSent?: () => void;
}

export function LineItemSidebar({
  quote,
  activeItemId,
  editable,
  onSelect,
  onAddItem,
  onVendorRfqSent,
}: LineItemSidebarProps) {
  const { t } = useTranslation();
  const [checked, setChecked] = useState<string[]>([]);
  const [rfqOpen, setRfqOpen] = useState(false);

  return (
    <aside className="est-line-item-sidebar" aria-label={t('estimating.line_items')}>
      <header className="est-sidebar-header">
        <span className="est-sidebar-quote">{t('estimating.title', { number: quote.number })}</span>
        <span className={`quote-status-badge status-${quote.status}`}>
          {t(`quotes.status.${quote.status}`, quote.status)}
        </span>
      </header>
      <ul className="est-line-item-list">
        {quote.items.map((item) => (
          <li key={item.id} className="est-line-item-row">
            {/* Multi-select for the batch send. Outside the row <button> — a checkbox
                nested in a button is neither clickable nor valid HTML. */}
            <input
              type="checkbox"
              className="est-line-item-check"
              aria-label={t('vendorRfq.send_vendor_rfq')}
              checked={checked.includes(item.id)}
              onChange={() =>
                setChecked((prev) =>
                  prev.includes(item.id) ? prev.filter((x) => x !== item.id) : [...prev, item.id],
                )
              }
            />
            <button
              type="button"
              className={item.id === activeItemId ? 'est-line-item active' : 'est-line-item'}
              aria-current={item.id === activeItemId ? 'true' : undefined}
              onClick={() => onSelect(item.id)}
            >
              <span className="est-line-item-pos">{item.position}</span>
              <span className="est-line-item-body">
                <span className="est-line-item-status">
                  {t(`estimating.workflow_status.${item.workflow_status}`, item.workflow_status)}
                </span>
                {item.awaiting_vendor_responses > 0 && (
                  <span className="est-chip est-chip-awaiting" role="status">
                    {t('vendorRfq.awaiting', { count: item.awaiting_vendor_responses })}
                  </span>
                )}
              </span>
              {item.priority != null && (
                <span className="est-line-item-priority" title={t('estimating.priority')}>
                  {item.priority}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
      {quote.items.length === 0 && (
        <p className="est-sidebar-empty">{t('estimating.no_line_items')}</p>
      )}
      {checked.length > 0 && (
        <button
          type="button"
          className="btn btn-secondary est-send-vendor-rfq"
          disabled={!editable}
          onClick={() => setRfqOpen(true)}
        >
          {t('vendorRfq.send_vendor_rfq')}
        </button>
      )}
      <button type="button" className="est-add-line-item" onClick={onAddItem} disabled={!editable}>
        {t('estimating.add_line_item')}
      </button>
      {rfqOpen && (
        <VendorRfqBatchModal
          quoteId={quote.id}
          quoteItemIds={checked}
          onClose={() => setRfqOpen(false)}
          onSent={() => {
            setRfqOpen(false);
            setChecked([]);
            onVendorRfqSent?.();
          }}
        />
      )}
    </aside>
  );
}
