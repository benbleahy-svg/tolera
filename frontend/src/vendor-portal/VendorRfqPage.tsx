/**
 * Vendor-RFQ portal page (M6.2): the PUBLIC, unauthenticated, white-label RFQ
 * response form at `/vendor-rfq/:token` (spec `#vendor-rfq`, "Vendor Portal").
 *
 * Renders the tenant-branded header, the parts table (part no/rev/description/
 * process/qty breaks/estimator notes/granted file downloads), the Download-RFQ-PDF
 * link, and the per-line response form (unit price + lead time per quantity break,
 * a "cannot quote this part" checkbox for a partial response) plus the quote-level
 * valid-until and notes.
 *
 * **The portal never closes.** Past the need-by date the page shows an informational
 * note and stays fully submittable — the server accepts the late response and stamps
 * it (spec "Soft cutoff behaviour"). There is no disabled state keyed on the date.
 *
 * Prices are held as raw strings and posted verbatim: parsing them into JS numbers
 * would round the money the shop is about to be charged.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { LegalFooter } from '../shared/LegalFooter';
import { fetchVendorRfq, submitVendorResponse, vendorFileUrl, vendorPdfUrl } from './api';
import type { VendorRfq, VendorRfqLine, VendorResponseRequest } from './types';

/** The form state for one line: its per-quantity cells plus the line-level flags. */
interface LineDraft {
  cannotQuote: boolean;
  notes: string;
  /** keyed by quantity → { price, lead } as typed (strings, never numbers) */
  cells: Map<number, { price: string; lead: string }>;
}

type DraftMap = Map<string, LineDraft>;

function emptyDraft(line: VendorRfqLine): LineDraft {
  return {
    cannotQuote: false,
    notes: '',
    cells: new Map(line.quantities.map((q) => [q, { price: '', lead: '' }])),
  };
}

/** Seed the form from any prior submission so a correction is an edit, not a retype. */
function initialDrafts(rfq: VendorRfq): DraftMap {
  const drafts: DraftMap = new Map();
  for (const line of rfq.lines) {
    const draft = emptyDraft(line);
    const prior = rfq.response?.lines.find((l) => l.rfq_line_id === line.id);
    if (prior) {
      draft.cannotQuote = prior.cannot_quote;
      draft.notes = prior.notes ?? '';
      for (const price of prior.prices) {
        draft.cells.set(price.quantity, {
          price: price.unit_price ?? '',
          lead: price.lead_time_days == null ? '' : String(price.lead_time_days),
        });
      }
    }
    drafts.set(line.id, draft);
  }
  return drafts;
}

function formatDate(iso: string, locale: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(locale, { dateStyle: 'long' }).format(date);
}

/** Build the wire payload — a `cannot quote` line deliberately carries no prices. */
function toRequest(
  rfq: VendorRfq,
  drafts: DraftMap,
  currency: string,
  validUntil: string,
  notes: string,
): VendorResponseRequest {
  return {
    currency,
    valid_until: validUntil || null,
    notes: notes || null,
    lines: rfq.lines.map((line) => {
      const draft = drafts.get(line.id) ?? emptyDraft(line);
      const prices = draft.cannotQuote
        ? []
        : [...draft.cells.entries()]
            .filter(([, cell]) => cell.price.trim() !== '' || cell.lead.trim() !== '')
            .map(([quantity, cell]) => ({
              quantity,
              unit_price: cell.price.trim() === '' ? null : cell.price.trim(),
              lead_time_days: cell.lead.trim() === '' ? null : Number(cell.lead.trim()),
            }));
      return {
        rfq_line_id: line.id,
        cannot_quote: draft.cannotQuote,
        notes: draft.notes || null,
        prices,
      };
    }),
  };
}

export function VendorRfqPage() {
  const { t } = useTranslation();
  const { token } = useParams<{ token: string }>();
  const [rfq, setRfq] = useState<VendorRfq | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [drafts, setDrafts] = useState<DraftMap>(new Map());
  const [currency, setCurrency] = useState('EUR');
  const [validUntil, setValidUntil] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submittedAt, setSubmittedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setFailed(false);
    // Reset per-RFQ state when the token changes so one batch's draft can never
    // bleed into another's (line ids differ, but the quote-level fields would).
    setRfq(null);
    setDrafts(new Map());
    setSubmittedAt(null);
    setError(null);
    if (!token) {
      setFailed(true);
      setLoading(false);
      return;
    }
    fetchVendorRfq(token)
      .then((data) => {
        if (!active) return;
        setRfq(data);
        setDrafts(initialDrafts(data));
        setCurrency(data.response?.currency ?? 'EUR');
        setValidUntil(data.response?.valid_until ?? '');
        setNotes(data.response?.notes ?? '');
        setSubmittedAt(data.response?.submitted_at ?? null);
        setLoading(false);
      })
      .catch(() => {
        if (!active) return;
        setFailed(true);
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token]);

  const locale = rfq?.shop.locale ?? 'de-DE';
  const hasAnswer = useMemo(
    () =>
      [...drafts.values()].some(
        (d) => d.cannotQuote || [...d.cells.values()].some((c) => c.price.trim() !== ''),
      ),
    [drafts],
  );

  function updateDraft(lineId: string, apply: (draft: LineDraft) => LineDraft) {
    setDrafts((prev) => {
      const next = new Map(prev);
      const current = next.get(lineId);
      if (current) next.set(lineId, apply(current));
      return next;
    });
  }

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!token || !rfq || submitting) return;
    setSubmitting(true);
    setError(null);
    submitVendorResponse(token, toRequest(rfq, drafts, currency, validUntil, notes))
      .then((result) => {
        setSubmittedAt(result.submitted_at);
        setSubmitting(false);
      })
      .catch(() => {
        setError(t('vendorPortal.submit_failed'));
        setSubmitting(false);
      });
  }

  if (loading) {
    return <div className="portal-state">{t('vendorPortal.loading')}</div>;
  }
  if (failed || !rfq) {
    return (
      <div className="portal-state portal-error" role="alert">
        <p>{t('vendorPortal.invalid_link')}</p>
      </div>
    );
  }

  return (
    <div className="portal">
      <header className="portal-header">
        <h1 className="portal-shop-name">{rfq.shop.name}</h1>
        <div className="portal-meta">
          <span>{t('vendorPortal.rfq_number', { number: rfq.rfq_number })}</span>
          {rfq.need_by_date && (
            <span>
              {t('vendorPortal.need_by', { date: formatDate(rfq.need_by_date, locale) })}
            </span>
          )}
          <a href={vendorPdfUrl(token!)} target="_blank" rel="noreferrer">
            {t('vendorPortal.download_pdf')}
          </a>
        </div>
      </header>

      <p className="portal-vendor">{t('vendorPortal.addressed_to', { vendor: rfq.vendor.name })}</p>

      {/* Soft cutoff: informational only — nothing below is disabled by it. */}
      {rfq.is_past_due && <p className="portal-note">{t('vendorPortal.past_due_note')}</p>}

      {rfq.message && <p className="portal-message">{rfq.message}</p>}

      {submittedAt && (
        <p className="portal-success" role="status">
          {t('vendorPortal.submitted_at', { date: formatDate(submittedAt, locale) })}
        </p>
      )}

      <form onSubmit={onSubmit} className="vendor-rfq-form">
        {rfq.lines.map((line) => {
          const draft = drafts.get(line.id) ?? emptyDraft(line);
          return (
            <section key={line.id} className="vendor-rfq-line">
              <h2>
                {line.part_number ?? t('vendorPortal.untitled_part')}
                {line.revision ? ` · ${t('vendorPortal.revision', { rev: line.revision })}` : ''}
              </h2>
              {line.description && <p className="portal-muted">{line.description}</p>}
              <dl className="vendor-rfq-facts">
                <dt>{t('vendorPortal.process')}</dt>
                <dd>{line.process ?? '—'}</dd>
                {line.estimator_notes && (
                  <>
                    <dt>{t('vendorPortal.estimator_notes')}</dt>
                    <dd>{line.estimator_notes}</dd>
                  </>
                )}
              </dl>

              {line.files.length > 0 && (
                <ul className="vendor-rfq-files">
                  {line.files.map((file) => (
                    <li key={file.id}>
                      <a href={vendorFileUrl(token!, file.id)} target="_blank" rel="noreferrer">
                        {file.filename}
                      </a>
                    </li>
                  ))}
                </ul>
              )}

              <label className="vendor-rfq-cannot">
                <input
                  type="checkbox"
                  checked={draft.cannotQuote}
                  onChange={(e) =>
                    updateDraft(line.id, (d) => ({ ...d, cannotQuote: e.target.checked }))
                  }
                />
                {t('vendorPortal.cannot_quote')}
              </label>

              {/* A "cannot quote" line hides its price grid: the server refuses a
                  contradictory submission, so the UI must not invite one. */}
              {!draft.cannotQuote && (
                <table className="vendor-rfq-prices">
                  <thead>
                    <tr>
                      <th>{t('vendorPortal.quantity')}</th>
                      <th>{t('vendorPortal.unit_price')}</th>
                      <th>{t('vendorPortal.lead_time_days')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {line.quantities.map((quantity) => {
                      const cell = draft.cells.get(quantity) ?? { price: '', lead: '' };
                      return (
                        <tr key={quantity}>
                          <th scope="row">{quantity}</th>
                          <td>
                            <input
                              type="text"
                              inputMode="decimal"
                              value={cell.price}
                              aria-label={t('vendorPortal.unit_price_for', {
                                quantity,
                                part: line.part_number ?? '',
                              })}
                              onChange={(e) => {
                                const value = e.target.value;
                                updateDraft(line.id, (d) => {
                                  const cells = new Map(d.cells);
                                  cells.set(quantity, { ...cell, price: value });
                                  return { ...d, cells };
                                });
                              }}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              min={0}
                              value={cell.lead}
                              aria-label={t('vendorPortal.lead_time_for', {
                                quantity,
                                part: line.part_number ?? '',
                              })}
                              onChange={(e) => {
                                const value = e.target.value;
                                updateDraft(line.id, (d) => {
                                  const cells = new Map(d.cells);
                                  cells.set(quantity, { ...cell, lead: value });
                                  return { ...d, cells };
                                });
                              }}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}

              <label className="vendor-rfq-notes">
                {t('vendorPortal.line_notes')}
                <textarea
                  value={draft.notes}
                  onChange={(e) => {
                    const value = e.target.value;
                    updateDraft(line.id, (d) => ({ ...d, notes: value }));
                  }}
                />
              </label>
            </section>
          );
        })}

        <section className="vendor-rfq-footer">
          <label>
            {t('vendorPortal.currency')}
            <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
              <option value="EUR">EUR</option>
              <option value="CHF">CHF</option>
            </select>
          </label>
          <label>
            {t('vendorPortal.valid_until')}
            <input
              type="date"
              value={validUntil}
              onChange={(e) => setValidUntil(e.target.value)}
            />
          </label>
          <label>
            {t('vendorPortal.quote_notes')}
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
          {error && (
            <p className="portal-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" disabled={submitting || !hasAnswer}>
            {submitting ? t('vendorPortal.submitting') : t('vendorPortal.submit')}
          </button>
        </section>
      </form>
      <LegalFooter legal={rfq.legal} />
    </div>
  );
}
