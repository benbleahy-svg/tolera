/**
 * Requote Diff banner + panel (M4.12, spec #ai-requote-diff) — "Previous quote
 * found (Rev A …) — see what changed". Renders the deterministic diff (geometry
 * delta + drawing changes) and Claude's synthesis paragraph in the AI-Governor
 * purple, behind the explicit three-choice gate: Import router / Review
 * field-by-field / Start fresh. Nothing is copied without a click — the import
 * button is the only path that touches the router.
 */

import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { RequoteDiffEntry, RequoteFinding } from './types';

interface Props {
  entry: RequoteDiffEntry;
  busy: boolean;
  onImport: () => void;
  onReview: () => void;
  onStartFresh: () => void;
}

function findingLabel(finding: RequoteFinding): string {
  const base = finding.value ?? finding.normalized_value ?? finding.type;
  return finding.role ? `${finding.role}: ${base}` : base;
}

function toleranceLabel(tolerance: Record<string, unknown> | null): string {
  if (!tolerance) return '—';
  const upper = tolerance['upper'];
  const lower = tolerance['lower'];
  return `+${String(upper ?? '?')} / ${String(lower ?? '?')}`;
}

export function RequoteDiffPanel({
  entry,
  busy,
  onImport,
  onReview,
  onStartFresh,
}: Props): React.ReactElement {
  const { t } = useTranslation();
  const bodyId = useId();
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(false);

  const geo = entry.diff.geometry_delta;
  const findings = entry.diff.finding_diff;
  const changeCount =
    findings.added.length + findings.removed.length + findings.changed.length;

  return (
    <section className="requote-panel" data-testid="requote-panel" role="status">
      <div className="requote-banner">
        <span className="requote-badge">{t('requote.badge')}</span>{' '}
        {t('requote.banner', { number: entry.matched.quote_number })}{' '}
        <button
          type="button"
          className="requote-toggle"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? t('requote.hide_changes') : t('requote.see_changes')}
        </button>
      </div>

      {open && (
        <div className="requote-body" id={bodyId}>
          {entry.synthesis && (
            <p className="requote-synthesis" data-testid="requote-synthesis">
              {entry.synthesis}
            </p>
          )}
          {entry.ai && !entry.ai.enabled && (
            <p className="requote-ai-off">{t('requote.ai_off')}</p>
          )}

          <dl className="requote-signals">
            <div>
              <dt>{t('requote.geometry')}</dt>
              <dd>
                {geo.available && geo.volume
                  ? t('requote.geometry_delta', {
                      pct: geo.volume.delta_pct.toLocaleString('de-DE'),
                    })
                  : t('requote.geometry_unavailable')}
                {geo.significant && (
                  <strong className="requote-significant">
                    {' '}
                    {t('requote.significant')}
                  </strong>
                )}
              </dd>
            </div>
            <div>
              <dt>{t('requote.drawing_changes')}</dt>
              <dd>
                {changeCount === 0
                  ? t('requote.no_drawing_changes')
                  : t('requote.drawing_summary', {
                      added: findings.added.length,
                      removed: findings.removed.length,
                      changed: findings.changed.length,
                    })}
              </dd>
            </div>
          </dl>

          {detail && (
            <ul className="requote-findings" data-testid="requote-findings">
              {findings.added.map((f, i) => (
                <li key={`a${i}`}>
                  <span className="requote-chip added">{t('requote.added')}</span>{' '}
                  {findingLabel(f)}
                </li>
              ))}
              {findings.removed.map((f, i) => (
                <li key={`r${i}`}>
                  <span className="requote-chip removed">{t('requote.removed')}</span>{' '}
                  {findingLabel(f)}
                </li>
              ))}
              {findings.changed.map((c, i) => (
                <li key={`c${i}`}>
                  <span className="requote-chip changed">{t('requote.changed')}</span>{' '}
                  {findingLabel(c.b)}
                  {c.changes.includes('tolerance') && (
                    <>
                      {' — '}
                      {toleranceLabel(c.a.tolerance)} → {toleranceLabel(c.b.tolerance)}
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}

          <div className="requote-actions">
            <button
              type="button"
              className="requote-action primary"
              disabled={busy}
              onClick={onImport}
            >
              {t('requote.import_router', { number: entry.matched.quote_number })}
            </button>
            <button
              type="button"
              className="requote-action"
              disabled={busy}
              onClick={() => {
                setDetail(true);
                onReview();
              }}
            >
              {t('requote.review_fields')}
            </button>
            <button
              type="button"
              className="requote-action"
              disabled={busy}
              onClick={onStartFresh}
            >
              {t('requote.start_fresh')}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
