/**
 * Bulk Create Line Items (M3.4 — spec #wingman "pre-fills Bulk Create Line
 * Items"; DemoB/04 is the frame): the RFQ-files chip with the ORIGINAL RFQ
 * badge, the Lens "line item information autofilled" banner (AI-Governor
 * purple — suggestions only), the editable spreadsheet (Part Number* / Rev /
 * Description / Quantities), ADD ROW, and the explicit CREATE LINE ITEMS
 * Accept — the only path that creates anything.
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { BulkCreatePrefill, BulkCreateRowBody, QuoteSummary } from './types';

interface EditableRow {
  part_number: string;
  revision: string;
  description: string;
  /** Free text, e.g. "1, 5, 20" — blank defaults to 1 (dialog copy). */
  quantities: string;
  /** The reviewed file-distribution binding (from the prefill preview);
   *  cleared when the part number is edited so Accept never binds files the
   *  human did not see previewed for THIS part number. */
  matchedPartId: string | null;
  /** The filenames that binding distributes — rendered under the part number
   *  so the reviewer actually SEES what Accept will attach. */
  matchedFilenames: string[];
}

interface Props {
  quoteId: string;
  getPrefill: (quoteId: string) => Promise<BulkCreatePrefill>;
  create: (quoteId: string, rows: BulkCreateRowBody[]) => Promise<QuoteSummary>;
  onCreated: (quote: QuoteSummary) => void;
  onClose: () => void;
}

const EMPTY_ROW: EditableRow = {
  part_number: '',
  revision: '',
  description: '',
  quantities: '',
  matchedPartId: null,
  matchedFilenames: [],
};

/** True when the field contains tokens that are neither plain nor grouped
 * integers — the user should see their input was ignored, not silently
 * defaulted (CodeRabbit minor). */
function hasIgnoredQuantityTokens(text: string): boolean {
  return text
    .split(/[,;\s]+/)
    .some((token) => token !== '' && !/^\d+$/.test(token) && !/^\d{1,3}(?:[.']\d{3})+$/.test(token));
}

/** Accepts plain integers and the German/Swiss grouped forms ("1.000",
 * "1'000" → 1000). `Number("1.000")` would silently yield 1 — a wrong lot
 * size feeding every later price — so grouping is parsed explicitly and
 * anything else is ignored. */
function parseQuantities(text: string): number[] {
  const seen = new Set<number>();
  for (const token of text.split(/[,;\s]+/)) {
    if (!token) continue;
    let digits: string | null = null;
    if (/^\d+$/.test(token)) digits = token;
    else if (/^\d{1,3}(?:[.']\d{3})+$/.test(token)) digits = token.replace(/[.']/g, '');
    if (digits === null) continue;
    const qty = Number(digits);
    if (Number.isInteger(qty) && qty >= 1) seen.add(qty);
  }
  return [...seen].sort((a, b) => a - b);
}

export function BulkCreateDialog({ quoteId, getPrefill, create, onCreated, onClose }: Props) {
  const { t } = useTranslation();
  const [prefill, setPrefill] = useState<BulkCreatePrefill | null>(null);
  const [rows, setRows] = useState<EditableRow[]>([EMPTY_ROW]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPrefill(quoteId)
      .then((data) => {
        setPrefill(data);
        if (data.rows.length > 0) {
          setRows(
            data.rows.map((row) => ({
              part_number: row.part_number,
              revision: row.revision ?? '',
              description: row.description ?? '',
              quantities: row.quantities.join(', '),
              matchedPartId: row.matched_part_id,
              matchedFilenames: row.matched_filenames,
            })),
          );
        }
      })
      .catch((e: unknown) => setError(String(e instanceof Error ? e.message : e)));
  }, [getPrefill, quoteId]);

  // ESC closes (native dialog affordance the modal div lacks).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Modal focus management (CodeRabbit): focus lands on the first control
  // when the dialog opens, and Tab/Shift+Tab wrap inside it.
  const containerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const focusables = () =>
      Array.from(
        container.querySelectorAll<HTMLElement>('button, input, [tabindex]:not([tabindex="-1"])'),
      ).filter((el) => !el.hasAttribute('disabled'));
    focusables()[0]?.focus();
    const trap = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const els = focusables();
      if (els.length === 0) return;
      const first = els[0];
      const last = els[els.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    container.addEventListener('keydown', trap);
    return () => container.removeEventListener('keydown', trap);
  }, []);

  const setCell = (index: number, field: 'part_number' | 'revision' | 'description' | 'quantities', value: string) => {
    setRows((current) =>
      current.map((row, i) =>
        i === index
          ? {
              ...row,
              [field]: value,
              // An edited part number invalidates the previewed binding.
              matchedPartId: field === 'part_number' ? null : row.matchedPartId,
              matchedFilenames: field === 'part_number' ? [] : row.matchedFilenames,
            }
          : row,
      ),
    );
  };

  const autofilled = prefill?.status === 'completed' && prefill.rows.length > 0;
  const valid = rows.some((row) => row.part_number.trim() !== '');

  const submit = () => {
    const body: BulkCreateRowBody[] = rows
      .filter((row) => row.part_number.trim() !== '')
      .map((row) => ({
        part_number: row.part_number.trim(),
        revision: row.revision.trim() || null,
        description: row.description.trim() || null,
        // Blank quantities default to 1 server-side (the dialog's own copy).
        quantities: parseQuantities(row.quantities),
        matched_part_id: row.matchedPartId,
      }));
    if (body.length === 0) return;
    setBusy(true);
    setError(null);
    create(quoteId, body)
      .then(onCreated)
      .catch((e: unknown) => {
        setError(String(e instanceof Error ? e.message : e));
        setBusy(false);
      });
  };

  return (
    <div
      ref={containerRef}
      className="est-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label={t('bulk_create.title')}
    >
      <div className="est-modal bulk-create-modal">
        <h3>{t('bulk_create.title')}</h3>
        <p className="bulk-create-intro">
          {t('bulk_create.intro')} {t('bulk_create.intro_defaults')}
        </p>

        {prefill && prefill.rfq_files.length > 0 && (
          <div className="bulk-create-rfq-files">
            <span className="est-field-label">{t('bulk_create.rfq_files')}</span>
            {prefill.rfq_files.map((file) => (
              <span key={file.filename} className="bulk-create-file-chip">
                {file.filename}
                {file.original_rfq && (
                  <span className="bulk-create-original-badge">
                    {t('bulk_create.original_rfq')}
                  </span>
                )}
              </span>
            ))}
          </div>
        )}

        {autofilled && prefill?.found_in && (
          <p className="bulk-create-autofill-banner" role="status">
            <span aria-hidden="true">✦ </span>
            <strong>{t('bulk_create.autofilled')}</strong>{' '}
            {t('bulk_create.found_in', { file: prefill.found_in })}
          </p>
        )}
        {prefill?.status === 'failed' && (
          <p className="bulk-create-parse-failed" role="status">
            {t('bulk_create.parse_failed')}
          </p>
        )}
        {prefill?.status === 'pending' && (
          <p className="bulk-create-parse-failed" role="status">
            {t('bulk_create.parse_pending')}
          </p>
        )}

        {error && (
          <p className="est-error" role="alert">
            {error}
          </p>
        )}

        <table className="bulk-create-table">
          <thead>
            <tr>
              <th aria-label={t('bulk_create.col_row')} />
              <th>{t('bulk_create.col_part_number')}</th>
              <th>{t('bulk_create.col_revision')}</th>
              <th>{t('bulk_create.col_description')}</th>
              <th>{t('bulk_create.col_quantities')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              // Positional spreadsheet rows — the index IS the identity here.
              <tr key={index}>
                <td className="bulk-create-row-no">{index + 1}</td>
                <td>
                  <input
                    value={row.part_number}
                    aria-label={t('bulk_create.part_number_input', { row: index + 1 })}
                    onChange={(e) => setCell(index, 'part_number', e.target.value)}
                  />
                  {row.matchedFilenames.length > 0 && (
                    <p className="bulk-create-matched-files">
                      {t('bulk_create.matched_files', {
                        files: row.matchedFilenames.join(', '),
                      })}
                    </p>
                  )}
                </td>
                <td>
                  <input
                    value={row.revision}
                    aria-label={t('bulk_create.revision_input', { row: index + 1 })}
                    onChange={(e) => setCell(index, 'revision', e.target.value)}
                  />
                </td>
                <td>
                  <input
                    value={row.description}
                    aria-label={t('bulk_create.description_input', { row: index + 1 })}
                    onChange={(e) => setCell(index, 'description', e.target.value)}
                  />
                </td>
                <td>
                  <input
                    value={row.quantities}
                    aria-label={t('bulk_create.quantities_input', { row: index + 1 })}
                    placeholder={t('bulk_create.quantities_placeholder')}
                    onChange={(e) => setCell(index, 'quantities', e.target.value)}
                  />
                  {hasIgnoredQuantityTokens(row.quantities) && (
                    <p className="bulk-create-qty-warning" role="status">
                      {t('bulk_create.quantities_ignored')}
                    </p>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button
          type="button"
          className="bulk-create-add-row"
          onClick={() => setRows((current) => [...current, EMPTY_ROW])}
        >
          {t('bulk_create.add_row')}
        </button>

        <div className="est-actions">
          <button type="button" onClick={onClose} disabled={busy}>
            {t('common.cancel')}
          </button>
          <button
            type="button"
            className="bulk-create-submit"
            onClick={submit}
            disabled={!valid || busy}
          >
            {t('bulk_create.create_line_items')}
          </button>
        </div>
      </div>
    </div>
  );
}
