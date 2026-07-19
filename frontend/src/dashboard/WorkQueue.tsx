/**
 * The work queue (M6.1, spec #newscope §2) — "What needs me now": one merged,
 * prioritised list across quotes needing my action, tasks, review items, vendor
 * RFQs and @mentions.
 *
 * Presentational by design: the page fetches, this renders. Each row shows the
 * source, the entity, **why it surfaced** (reason chips) and its urgency, with
 * the four contributing factors revealed on hover/expand — the ordering has to
 * be explainable, not magic, so the numbers are always one interaction away.
 *
 * Cross-org rows (only @mentions can be — DECISIONS.md 2026-06-19 E4-a) are
 * labelled with their org. Selecting one is meant to switch active org, which
 * the M0.4 switcher still cannot do (token re-mint is M5.12), so the control is
 * disabled with the very same hint the switcher shows rather than pretending.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { QueueRow, UrgencyFactor } from './workQueueApi';

/** Fixed 4-dp strings from the API; show 2 dp — the extra digits only exist to
 *  make the ordering exact, and are visible in the factor panel. */
function formatScore(value: string, locale: string): string {
  return Number(value).toLocaleString(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function FactorPanel({
  factors,
  id,
}: {
  factors: UrgencyFactor[];
  /** Matches the toggle's `aria-controls` so assistive tech knows which button
   *  reveals which panel — one row's toggle must not claim another's table. */
  id: string;
}): React.ReactElement {
  const { t } = useTranslation();
  return (
    <table className="queue-factors" data-testid="queue-factors" id={id}>
      <thead>
        <tr>
          <th>{t('work_queue.factor')}</th>
          <th>{t('work_queue.factor_raw')}</th>
          <th>{t('work_queue.factor_weight')}</th>
          <th>{t('work_queue.factor_contribution')}</th>
        </tr>
      </thead>
      <tbody>
        {factors.map((factor) => (
          <tr key={factor.key} data-testid={`factor-${factor.key}`}>
            <td>{t(`work_queue.factor_${factor.key}`)}</td>
            <td>{factor.raw === '' ? '—' : factor.raw}</td>
            <td>{factor.weight}</td>
            <td>{factor.contribution}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RowLink({ row }: { row: QueueRow }): React.ReactElement {
  const { t } = useTranslation();
  if (row.cross_org) {
    // Switch-on-select is the intent (E4-a); the switch itself lands in M5.12.
    return (
      <span className="queue-cross-org-hint" title={t('org.switch_unavailable')}>
        {t('org.switch_unavailable')}
      </span>
    );
  }
  return <Link to={row.deep_link}>{t('work_queue.open')}</Link>;
}

export function WorkQueue({
  rows,
  locale,
}: {
  rows: QueueRow[];
  locale: string;
}): React.ReactElement {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<string | null>(null);

  if (rows.length === 0) {
    return <p className="dashboard-empty">{t('work_queue.empty')}</p>;
  }

  return (
    <ul className="work-queue">
      {rows.map((row) => {
        const key = `${row.source}:${row.id}`;
        const panelId = `queue-factors-${key}`;
        const open = expanded === key;
        return (
          <li key={key} className="queue-row" data-testid="queue-row" data-source={row.source}>
            <span className={`queue-source queue-source-${row.source}`}>
              {t(`work_queue.source_${row.source}`)}
            </span>
            <span className="queue-label">{row.label || t('work_queue.untitled')}</span>
            <span className="queue-chips">
              {row.reason_chips.map((chip) => (
                <span key={chip.key} className="queue-chip" data-testid="queue-chip">
                  {t(chip.key, chip.params)}
                </span>
              ))}
            </span>
            {row.cross_org && (
              <span className="queue-org-badge" data-testid="queue-org-badge">
                {row.org_name}
              </span>
            )}
            <button
              type="button"
              className="queue-urgency"
              aria-expanded={open}
              aria-controls={panelId}
              // Hover shows the same numbers the panel does (spec: "show the
              // contributing factors on hover"); the click target keeps it
              // reachable by keyboard and on touch.
              title={row.factors
                .map((f) => `${t(`work_queue.factor_${f.key}`)}: ${f.contribution}`)
                .join(' · ')}
              onClick={() => setExpanded(open ? null : key)}
            >
              {formatScore(row.urgency, locale)}
            </button>
            <RowLink row={row} />
            {open && <FactorPanel factors={row.factors} id={panelId} />}
          </li>
        );
      })}
    </ul>
  );
}
