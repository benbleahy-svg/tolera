/**
 * RFQ Triage Brief card (M3.9, spec #ai-triage) — the structured replacement
 * for the plain "New quote from email" notification. Renders the deterministic
 * signals (parts/file summary, missing-file blocker, detected processes,
 * est-time, need-by, compliance flags) and a clear "AI processing disabled"
 * state when the AI enrichment was skipped. Informational only — the assignee
 * chip is one click, never an auto-action.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useQuotesApi } from '../quotes/api';
import type { TriageBrief } from '../quotes/types';

interface Props {
  quoteId: string;
  quoteNumber: string;
}

export function TriageCard({ quoteId, quoteNumber }: Props): React.ReactElement {
  const { t } = useTranslation();
  const api = useQuotesApi();
  const [brief, setBrief] = useState<TriageBrief | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const res = await api.getTriageBrief(quoteId);
        if (alive) {
          setBrief(res.brief);
          setStatus('ready');
        }
      } catch {
        if (alive) setStatus('error');
      }
    })();
    return () => {
      alive = false;
    };
  }, [api, quoteId]);

  if (status === 'error') {
    return <div className="triage-card triage-card-pending">{t('triage.unavailable')}</div>;
  }
  if (status === 'loading' || brief === null) {
    return <div className="triage-card triage-card-pending">{t('triage.pending')}</div>;
  }

  const aiOff = !brief.ai.enabled;

  return (
    <div className="triage-card" data-testid="triage-card">
      <div className="triage-card-header">
        <strong>{t('triage.title', { number: quoteNumber })}</strong>
      </div>
      <dl className="triage-signals">
        <div className="triage-signal">
          <dt>{t('triage.parts')}</dt>
          <dd data-testid="triage-parts">
            {t('triage.parts_value', { count: brief.parts.count, files: brief.parts.files.summary })}
          </dd>
        </div>

        {brief.missing_files.length > 0 && (
          <div className="triage-signal triage-blocker" data-testid="triage-missing">
            <dt>⚠ {t('triage.missing_files')}</dt>
            <dd>{brief.missing_files.join(', ')}</dd>
          </div>
        )}

        <div className="triage-signal">
          <dt>{t('triage.processes')}</dt>
          <dd>
            {aiOff ? (
              <span className="triage-ai-off">{t('triage.ai_disabled')}</span>
            ) : brief.detected_processes.length > 0 ? (
              brief.detected_processes.map((p) => p.name).join(' · ')
            ) : (
              '—'
            )}
          </dd>
        </div>

        <div className="triage-signal">
          <dt>{t('triage.est_time')}</dt>
          <dd data-testid="triage-est-time">{brief.est_time_to_quote.display}</dd>
        </div>

        <div className="triage-signal">
          <dt>{t('triage.customer')}</dt>
          <dd>{brief.customer.one_liner}</dd>
        </div>

        {brief.compliance_flags.length > 0 && (
          <div className="triage-signal triage-compliance" data-testid="triage-compliance">
            <dt>⚠ {t('triage.compliance')}</dt>
            <dd>
              {brief.compliance_flags.map((f, i) => (
                <span key={i}>{f.detail}</span>
              ))}
            </dd>
          </div>
        )}

        <div className="triage-signal">
          <dt>{t('triage.need_by')}</dt>
          <dd>
            {brief.need_by.date
              ? t('triage.need_by_value', {
                  date: brief.need_by.date,
                  days: brief.need_by.days_until,
                  urgency: t(`triage.urgency_${brief.need_by.urgency}`),
                })
              : t('triage.urgency_keine')}
          </dd>
        </div>
      </dl>
    </div>
  );
}
