/**
 * Left line-item sidebar for the estimating screen (M5.0, spec #partview / DemoB 08):
 * the quote header, a selectable list of line items (with a priority badge), and the
 * "add line item" affordance. Selecting an item navigates to its spec route.
 */

import { useTranslation } from 'react-i18next';

import type { QuoteSummary } from './types';

interface LineItemSidebarProps {
  quote: QuoteSummary;
  activeItemId: string | null;
  editable: boolean;
  onSelect: (itemId: string) => void;
  onAddItem: () => void;
}

export function LineItemSidebar({
  quote,
  activeItemId,
  editable,
  onSelect,
  onAddItem,
}: LineItemSidebarProps) {
  const { t } = useTranslation();

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
          <li key={item.id}>
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
      <button type="button" className="est-add-line-item" onClick={onAddItem} disabled={!editable}>
        {t('estimating.add_line_item')}
      </button>
    </aside>
  );
}
