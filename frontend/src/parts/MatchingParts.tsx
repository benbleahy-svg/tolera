/**
 * "N passende Teile" — the Part-Library match chip + buckets modal (M2.12,
 * spec #partlib, DemoB/09 ground truth).
 *
 * <PartMatchesChip> fetches a part's matches and renders the count chip that
 * opens <MatchingPartsModal>: subject preview at the left, collapsible match
 * buckets (Exact File / Exact Geometric / File Name / Part Number / Similar
 * Geometries / Historical) with counts. The two geometry buckets render a
 * "pending M4" placeholder until GeometryService lands. Historical cards list
 * prior quotes; "Übernehmen" copies that quote's router + manual overrides
 * onto the current component (suggestion-accept is explicit — nothing is
 * imported without a click).
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ApiError } from '../api/client';
import {
  type MatchBucket,
  type MatchCard,
  type PartMatches,
  usePartsApi,
} from './api';

interface ChipProps {
  partId: string;
  /** Target component for "import historical work"; omit to hide import. */
  componentId?: string;
  editable?: boolean;
  /** Called after a successful import so the host refreshes its costing. */
  onImported?: () => void;
}

export function PartMatchesChip({ partId, componentId, editable, onImported }: ChipProps) {
  const { t } = useTranslation();
  // Destructured so the effect depends on the function, not the wrapper object
  // (an unstable wrapper identity must not clear-and-refetch on every render).
  const { getMatches } = usePartsApi();
  const [matches, setMatches] = useState<PartMatches | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setMatches(null);
    getMatches(partId)
      .then((m) => {
        if (!cancelled) setMatches(m);
      })
      .catch(() => {
        /* the chip simply stays hidden when matches can't load */
      });
    return () => {
      cancelled = true;
    };
  }, [getMatches, partId]);

  if (!matches || matches.total === 0) return null;
  return (
    <>
      <button
        type="button"
        className="crm-chip match-chip"
        data-testid="match-chip"
        onClick={() => setOpen(true)}
      >
        {t('parts.match.chip', { count: matches.total })}
      </button>
      {open && (
        <MatchingPartsModal
          matches={matches}
          componentId={componentId}
          editable={editable}
          onImported={onImported}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

interface ModalProps {
  matches: PartMatches;
  componentId?: string;
  editable?: boolean;
  onImported?: () => void;
  onClose: () => void;
}

export function MatchingPartsModal({
  matches,
  componentId,
  editable,
  onImported,
  onClose,
}: ModalProps) {
  const { t } = useTranslation();
  const api = usePartsApi();
  const dialogRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState<string | null>(
    matches.buckets.find((b) => b.count > 0)?.key ?? null,
  );
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState<string | null>(null);

  // Focus management (the CreateAccountModal pattern): move focus into the
  // dialog on open, trap Tab inside it, restore the opener's focus on close.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab' && dialogRef.current) {
        const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      opener?.focus();
    };
  }, [onClose]);

  const importFrom = (sourceComponentId: string) => {
    if (!componentId || importing) return;
    setImporting(sourceComponentId);
    setError(null);
    api
      .importRouter(componentId, sourceComponentId)
      .then(() => {
        onImported?.();
        onClose();
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)))
      .finally(() => setImporting(null));
  };

  const subject = matches.subject;
  return (
    <div
      className="crm-modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('parts.match.title', { count: matches.total })}
        className="crm-modal match-modal"
        data-testid="matching-parts-modal"
        ref={dialogRef}
        tabIndex={-1}
      >
        <header className="match-modal-header">
          <p className="match-modal-kicker">{t('parts.match.kicker')}</p>
          <h2>{t('parts.match.title', { count: matches.total })}</h2>
          <button type="button" className="btn btn-ghost" onClick={onClose} aria-label={t('common.close')}>
            ✕
          </button>
        </header>
        <div className="match-modal-body">
          <aside className="match-subject">
            <div className="match-thumb" aria-hidden="true">
              ▦
            </div>
            {subject.primary_filename && <p className="match-subject-file">{subject.primary_filename}</p>}
            <dl>
              <dt>{t('parts.match.part_number')}</dt>
              <dd>{subject.part_number ?? '—'}</dd>
              <dt>{t('parts.match.revision')}</dt>
              <dd>{subject.revision ?? '—'}</dd>
            </dl>
          </aside>
          <div className="match-buckets">
            {error && (
              <p className="crm-error" role="alert">
                {error}
              </p>
            )}
            {matches.buckets.map((bucket) => (
              <BucketRow
                key={bucket.key}
                bucket={bucket}
                expanded={expanded === bucket.key}
                onToggle={() => setExpanded(expanded === bucket.key ? null : bucket.key)}
                canImport={Boolean(componentId && editable)}
                importing={importing}
                onImport={importFrom}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

interface BucketRowProps {
  bucket: MatchBucket;
  expanded: boolean;
  onToggle: () => void;
  canImport: boolean;
  importing: string | null;
  onImport: (sourceComponentId: string) => void;
}

function BucketRow({ bucket, expanded, onToggle, canImport, importing, onImport }: BucketRowProps) {
  const { t } = useTranslation();
  const processing = bucket.status === 'processing';
  return (
    <section className="match-bucket">
      <button
        type="button"
        className="match-bucket-toggle"
        aria-expanded={expanded}
        data-testid={`bucket-${bucket.key}`}
        onClick={onToggle}
        disabled={processing}
      >
        <span>
          {t(`parts.match.bucket.${bucket.key}`)} ({bucket.count})
        </span>
        {processing && <span className="crm-chip">{t('parts.match.processing')}</span>}
      </button>
      {expanded && !processing && bucket.matches.length > 0 && (
        <ul className="match-cards">
          {bucket.matches.map((card) => (
            <MatchCardView
              key={card.part_id}
              card={card}
              canImport={canImport}
              importing={importing}
              onImport={onImport}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

interface CardProps {
  card: MatchCard;
  canImport: boolean;
  importing: string | null;
  onImport: (sourceComponentId: string) => void;
}

function MatchCardView({ card, canImport, importing, onImport }: CardProps) {
  const { t } = useTranslation();
  return (
    <li className="match-card" data-testid={`match-card-${card.part_id}`}>
      <header>
        <strong>
          {card.part_number ?? card.name ?? '—'}
          {card.revision
            ? ` · ${t('parts.match.revision_short', { revision: card.revision })}`
            : ''}
        </strong>
        {card.archived && <span className="crm-chip">{t('parts.library.badge_archived')}</span>}
      </header>
      {card.primary_filename && <p className="match-card-file">{card.primary_filename}</p>}
      <p className="match-card-quotes">
        {t('parts.match.quotes', { count: card.quote_count })}
        {card.quotes.map((ref) => (
          <span key={ref.quote_item_id} className="match-quote-ref">
            <Link to={`/quotes/${ref.quote_id}`}>{ref.number}</Link>
            {canImport && (
              <button
                type="button"
                className="btn btn-link"
                disabled={importing !== null}
                onClick={() => onImport(ref.component_id)}
              >
                {t('parts.match.import')}
              </button>
            )}
          </span>
        ))}
      </p>
    </li>
  );
}
