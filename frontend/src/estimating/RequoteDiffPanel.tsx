/**
 * Requote Diff banner + panel (M4.12, spec #ai-requote-diff) — "Previous quote
 * found (Rev A …) — see what changed". Renders the deterministic diff (geometry
 * delta + drawing changes) and Claude's synthesis paragraph in the AI-Governor
 * purple, behind the explicit three-choice gate: Import router / Review
 * field-by-field / Start fresh. Nothing is copied without a click — the import
 * button is the only path that touches the router.
 *
 * M4.13 (spec #ai-quote-assembly) shares this panel location: the assembly
 * offer ("quoted N times — draft from the most recent quote?") with the two
 * explicit-accept paths — Review (values chipped "AI-drafted") and Accept All
 * (atomic import + 60-second undo chip). Accept All only renders when the
 * server says `accept_all_eligible` — and the server re-checks on POST.
 */

import { useEffect, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { RequoteDiffEntry, RequoteFinding } from './types';

interface Props {
  entry: RequoteDiffEntry;
  busy: boolean;
  onImport: () => void;
  onReview: () => void;
  onStartFresh: () => void;
  onAcceptAll: () => void;
  onImportForReview: () => void;
  onUndo: () => void;
}

/** Seconds until `iso`, floored at 0 — the undo chip countdown. */
function secondsLeft(iso: string | null): number {
  if (!iso) return 0;
  return Math.max(0, Math.floor((Date.parse(iso) - Date.now()) / 1000));
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
  onAcceptAll,
  onImportForReview,
  onUndo,
}: Props): React.ReactElement {
  const { t, i18n } = useTranslation();
  const bodyId = useId();
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(false);

  const geo = entry.diff.geometry_delta;
  const findings = entry.diff.finding_diff;
  const changeCount =
    findings.added.length + findings.removed.length + findings.changed.length;

  const assemblyState = entry.assembly_state;
  const record = entry.assembly && !entry.assembly.undone_at ? entry.assembly : null;
  // Tick the undo countdown once a second while the window is open.
  const [undoLeft, setUndoLeft] = useState(() =>
    secondsLeft(record?.path === 'accept_all' ? record.undo_expires_at : null),
  );
  useEffect(() => {
    const expires = record?.path === 'accept_all' ? record.undo_expires_at : null;
    setUndoLeft(secondsLeft(expires));
    if (!expires) return;
    const timer = window.setInterval(() => {
      const left = secondsLeft(expires);
      setUndoLeft(left);
      if (left <= 0) window.clearInterval(timer);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [record]);

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

      {/* M4.13 — the assembly offer (only when the org's AI flags allow it).
          A currency mismatch (or a stale pre-M4.13 entry) blocks BOTH import
          paths server-side, so neither button is offered. */}
      {assemblyState?.offered &&
        !record &&
        (assemblyState.blockers.includes('currency_mismatch') ||
        assemblyState.blockers.includes('entry_stale') ? (
          <div className="requote-banner assembly-offer" data-testid="assembly-banner">
            {t('assembly.banner', { count: assemblyState.quote_count })}{' '}
            <span className="assembly-suppressed" data-testid="assembly-import-blocked">
              {t('assembly.import_blocked')}
            </span>
          </div>
        ) : (
          <div className="requote-banner assembly-offer" data-testid="assembly-banner">
            {t('assembly.banner', { count: assemblyState.quote_count })}{' '}
            {assemblyState.accept_all_eligible ? (
              <button
                type="button"
                className="requote-action primary"
                data-testid="assembly-accept-all"
                disabled={busy}
                onClick={onAcceptAll}
              >
                {t('assembly.accept_all')}
              </button>
            ) : (
              <span className="assembly-suppressed" data-testid="assembly-suppressed">
                {t('assembly.suppressed')}
              </span>
            )}{' '}
            <button
              type="button"
              className="requote-action"
              data-testid="assembly-review-import"
              disabled={busy}
              onClick={onImportForReview}
            >
              {t('assembly.review_import')}
            </button>
          </div>
        ))}

      {/* After an import: the audit line + the 60-second undo chip */}
      {/* aria-live="off": the per-second countdown must not be re-announced
          by the enclosing role="status" live region every tick */}
      {record && (
        <div
          className="requote-banner assembly-imported"
          data-testid="assembly-imported"
          aria-live="off"
        >
          {t('assembly.imported_note', {
            number: record.source_quote_number ?? '—',
            date: new Date(record.at).toLocaleDateString(
              i18n.language === 'de' ? 'de-DE' : 'en-IE',
            ),
          })}
          {record.path === 'review' && (
            <span className="lens-chip" data-status="suggested">
              {t('assembly.review_note')}
            </span>
          )}{' '}
          {record.path === 'accept_all' && undoLeft > 0 && (
            <button
              type="button"
              className="requote-action assembly-undo"
              data-testid="assembly-undo"
              disabled={busy}
              onClick={onUndo}
            >
              {t('assembly.undo', { seconds: undoLeft })}
            </button>
          )}
        </div>
      )}

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
