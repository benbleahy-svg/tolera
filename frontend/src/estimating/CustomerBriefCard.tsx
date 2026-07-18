/**
 * Customer Intelligence Brief — AI Feature 5 (M5.10, spec #ai-customer-brief).
 *
 * The collapsible "About [Account]" card at the top of the send-quote side
 * panel (above To/CC/BCC). Fetches the brief on mount and renders ONLY when the
 * backend returns bullets — there is deliberately no loading skeleton and no
 * empty state (spec: graceful degradation, the card is simply absent when the
 * account has < 3 prior quotes, the AI toggle is off, or the model call fails).
 *
 * AI-Governor framing: purple accent, informational. The brief is pure
 * information — the estimator reads it, applies their own judgement, and sends;
 * nothing is auto-applied. Dismissible per session (no persistence).
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useQuotesApi } from '../quotes/api';
import type { CustomerBrief } from '../quotes/types';

interface Props {
  quoteId: string;
}

export function CustomerBriefCard({ quoteId }: Props): React.ReactElement | null {
  const { t } = useTranslation();
  const api = useQuotesApi();
  const [brief, setBrief] = useState<CustomerBrief | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  // Reset all quote-scoped state when the quote changes: if this card is reused
  // for a different quote, the previous customer's brief must never linger while
  // the new one loads (or if the new one is omitted/empty/fails). Keyed on
  // quoteId alone so a user dismiss/collapse survives unrelated re-renders.
  useEffect(() => {
    setBrief(null);
    setDismissed(false);
    setCollapsed(false);
  }, [quoteId]);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const res = await api.getCustomerBrief(quoteId);
        // Only surface the card when the backend actually produced bullets.
        if (alive && res.brief && res.brief.bullets.length > 0) setBrief(res.brief);
      } catch {
        // Never block the composer on a brief failure — just show no card.
      }
    })();
    return () => {
      alive = false;
    };
  }, [api, quoteId]);

  // No card while loading, on failure, on graceful omission, or once dismissed.
  if (brief === null || dismissed) return null;

  return (
    <section className="customer-brief-card" data-testid="customer-brief-card" aria-live="polite">
      <div className="customer-brief-header">
        <button
          type="button"
          className="customer-brief-toggle"
          aria-expanded={!collapsed}
          onClick={() => setCollapsed((c) => !c)}
        >
          <span className="customer-brief-title">
            {t('customerBrief.title', { account: brief.account_name })}
          </span>
          <span className="customer-brief-caret" aria-hidden="true">
            {collapsed ? '▸' : '▾'}
          </span>
        </button>
        <button
          type="button"
          className="customer-brief-dismiss"
          aria-label={t('customerBrief.dismiss')}
          onClick={() => setDismissed(true)}
        >
          ×
        </button>
      </div>
      {!collapsed && (
        <ul className="customer-brief-bullets">
          {brief.bullets.map((bullet, i) => (
            <li key={i}>{bullet}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
