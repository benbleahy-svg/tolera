/**
 * Lead Times + Expedite (M1.11, spec #addons; KB dynamic-lead-times-guide):
 * per quantity break — the base lead time (calc from process/material/DAYS,
 * blue-text editable) and the expedite rows (days faster + % markup → shorter
 * lead, higher price). The tier editor writes this line's expedite options;
 * APPLY TO ALL pushes the standard lead time + tiers to every line item.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ExpediteTierBody, PricingSummary } from './types';

interface Props {
  pricing: PricingSummary;
  formatMoney: (value: string | null) => string;
  editable: boolean;
  onLeadTimeOverride: (quantity: number, manualLeadTimeDays: number | null) => void;
  onSetExpediteOptions: (options: ExpediteTierBody[]) => void;
  onApplyToAll: (standardLeadTimeDays: number | null, tiers: ExpediteTierBody[]) => void;
}

function parseTiers(daysA: string, pctA: string, daysB: string, pctB: string): ExpediteTierBody[] {
  const tiers: ExpediteTierBody[] = [];
  if (daysA.trim() && pctA.trim()) {
    tiers.push({ days_faster: Number(daysA), markup_pct: pctA.trim().replace(',', '.') });
  }
  if (daysB.trim() && pctB.trim()) {
    tiers.push({ days_faster: Number(daysB), markup_pct: pctB.trim().replace(',', '.') });
  }
  return tiers;
}

export function LeadTimesSection({
  pricing,
  formatMoney,
  editable,
  onLeadTimeOverride,
  onSetExpediteOptions,
  onApplyToAll,
}: Props) {
  const { t } = useTranslation();
  const [editingQty, setEditingQty] = useState<number | null>(null);
  const [draft, setDraft] = useState('');
  // the tier editor (two slots cover the common case; the API takes any count)
  const [standard, setStandard] = useState('');
  const [daysA, setDaysA] = useState('');
  const [pctA, setPctA] = useState('');
  const [daysB, setDaysB] = useState('');
  const [pctB, setPctB] = useState('');

  const expediteCount = Math.max(0, ...pricing.lead_times.map((lt) => lt.expedites.length));

  return (
    <section className="est-section">
      <h3>{t('pricing.lead_times_title')}</h3>
      <table className="est-table">
        <thead>
          <tr>
            <th>{t('pricing.quantity')}</th>
            <th>{t('pricing.lead_time')}</th>
            {Array.from({ length: expediteCount }, (_, i) => (
              <th key={i}>{t('pricing.expedite_option', { index: i + 1 })}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {pricing.lead_times.map((row) => (
            <tr key={row.quantity}>
              <td>{row.quantity}</td>
              {editingQty === row.quantity ? (
                <td>
                  <input
                    autoFocus
                    className="est-cell-input"
                    value={draft}
                    aria-label={t('pricing.lead_time_override_label', { qty: row.quantity })}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        const trimmed = draft.trim();
                        onLeadTimeOverride(row.quantity, trimmed === '' ? null : Number(trimmed));
                        setEditingQty(null);
                      }
                      if (e.key === 'Escape') setEditingQty(null);
                    }}
                    onBlur={() => setEditingQty(null)}
                  />
                </td>
              ) : (
                <td>
                  <button
                    type="button"
                    className="est-cell-button"
                    disabled={!editable}
                    aria-label={t('pricing.lead_time_override_label', { qty: row.quantity })}
                    onClick={() => {
                      setDraft(row.lead_time_days == null ? '' : String(row.lead_time_days));
                      setEditingQty(row.quantity);
                    }}
                  >
                    <span
                      className={row.manual_lead_time_days != null ? 'est-overridden' : undefined}
                    >
                      {row.lead_time_days == null
                        ? '—'
                        : t('pricing.days', { count: row.lead_time_days })}
                      {row.manual_lead_time_days != null && ' *'}
                    </span>
                  </button>
                </td>
              )}
              {Array.from({ length: expediteCount }, (_, i) => {
                const expedite = row.expedites[i];
                if (!expedite) return <td key={i} />;
                return (
                  <td key={i} className="est-num">
                    {expedite.lead_time_days == null
                      ? '—'
                      : t('pricing.days', { count: expedite.lead_time_days })}
                    <br />
                    <small>
                      {formatMoney(expedite.unit_price)} (+{Number(expedite.markup_pct)} %)
                    </small>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="est-inline-form">
        <label>
          {t('pricing.standard_lead_time')}
          <input
            value={standard}
            aria-label={t('pricing.standard_lead_time')}
            onChange={(e) => setStandard(e.target.value)}
            size={4}
          />
        </label>
        <label>
          {t('pricing.days_faster')}
          <input value={daysA} aria-label={`${t('pricing.days_faster')} 1`} size={3}
            onChange={(e) => setDaysA(e.target.value)} />
        </label>
        <label>
          {t('pricing.markup_pct')}
          <input value={pctA} aria-label={`${t('pricing.markup_pct')} 1`} size={4}
            onChange={(e) => setPctA(e.target.value)} />
        </label>
        <label>
          {t('pricing.days_faster')}
          <input value={daysB} aria-label={`${t('pricing.days_faster')} 2`} size={3}
            onChange={(e) => setDaysB(e.target.value)} />
        </label>
        <label>
          {t('pricing.markup_pct')}
          <input value={pctB} aria-label={`${t('pricing.markup_pct')} 2`} size={4}
            onChange={(e) => setPctB(e.target.value)} />
        </label>
        <button
          type="button"
          disabled={!editable}
          onClick={() => onSetExpediteOptions(parseTiers(daysA, pctA, daysB, pctB))}
        >
          {t('pricing.set_expedites')}
        </button>
        <button
          type="button"
          disabled={!editable}
          onClick={() =>
            onApplyToAll(
              standard.trim() === '' ? null : Number(standard),
              parseTiers(daysA, pctA, daysB, pctB),
            )
          }
        >
          {t('pricing.apply_to_all')}
        </button>
      </div>
    </section>
  );
}
