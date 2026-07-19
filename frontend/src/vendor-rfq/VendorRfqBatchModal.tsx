/**
 * Vendor RFQ batch-send modal (M6.4, spec `#vendor-rfq` → "Batch send modal").
 *
 * One modal, two entry points: Quote Detail's line multi-select toolbar ("Send Vendor
 * RFQ") and the Part Estimating Outside-Services section ("Get Vendor Quote", with the
 * current line pre-selected). Both pass the same props — the modal does not care which
 * opened it, which is what keeps the two flows from drifting apart.
 *
 * Fields follow the spec exactly: the line-item checklist, the vendor multi-select
 * filtered to the lines' process types with the ranked suggestions pre-checked (**New**
 * labels on zero-history vendors), need-by, message, and a **per-vendor** file toggle
 * whose defaults prefer the redacted copy. Sending creates one blind, isolated RFQ per
 * vendor — the server does that; the modal just posts one batch.
 */

import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import {
  type ComposeLine,
  type ComposePayload,
  type CostingMode,
  type SendRecipient,
  useVendorRfqApi,
} from './api';

export function VendorRfqBatchModal({
  quoteId,
  quoteItemIds,
  onClose,
  onSent,
}: {
  quoteId: string;
  /** Lines pre-selected by the caller; the estimator may untick them in-modal. */
  quoteItemIds: string[];
  onClose: () => void;
  onSent: (count: number) => void;
}) {
  const { t } = useTranslation();
  const api = useVendorRfqApi();
  const dialogRef = useRef<HTMLDivElement>(null);

  const [compose, setCompose] = useState<ComposePayload | null>(null);
  // The line checklist is a **stable** snapshot of everything the caller offered.
  // The vendor list narrows to whatever is currently ticked, but the checklist must
  // not — a line unticked once has to be re-tickable, and the server only returns
  // the lines it was asked about.
  const [allLines, setAllLines] = useState<ComposeLine[]>([]);
  const [includeAllVendors, setIncludeAllVendors] = useState(false);
  const [selectedLines, setSelectedLines] = useState<string[]>(quoteItemIds);
  const [selectedVendors, setSelectedVendors] = useState<string[]>([]);
  // vendor id → the file ids that vendor receives (the spec's per-vendor toggle).
  const [vendorFiles, setVendorFiles] = useState<Record<string, string[]>>({});
  const [needBy, setNeedBy] = useState('');
  const [message, setMessage] = useState('');
  const [costingMode, setCostingMode] = useState<CostingMode | ''>('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Close on Escape and keep Tab focus inside the dialog (a11y for a modal).
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;
      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
        'button, input, textarea, select, a[href], [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable || focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  // Recompose whenever the line selection changes: the required process types (and
  // therefore which vendors are even offered) are derived from the selected lines.
  useEffect(() => {
    let cancelled = false;
    if (selectedLines.length === 0) {
      // Nothing ticked: no vendors to offer, but keep the checklist on screen so the
      // estimator can tick a line back on instead of being stuck in an empty modal.
      setCompose(null);
      return;
    }
    api
      .compose(quoteId, selectedLines, includeAllVendors)
      .then((payload) => {
        if (cancelled) return;
        setCompose(payload);
        // Grow the stable checklist; never shrink it (see `allLines`).
        setAllLines((prev) => {
          const seen = new Set(prev.map((l) => l.quote_item_id));
          return [...prev, ...payload.lines.filter((l) => !seen.has(l.quote_item_id))];
        });
        setSelectedVendors(payload.vendors.filter((v) => v.suggested).map((v) => v.id));
        // Seed a *newly offered* vendor's file allowlist with the defaults, but never
        // overwrite one the estimator has already adjusted — that allowlist is the
        // one setting here with disclosure consequences.
        const defaults = payload.lines.flatMap((line) => line.default_file_ids);
        setVendorFiles((prev) => {
          const next = { ...prev };
          for (const vendor of payload.vendors) {
            if (!(vendor.id in next)) next[vendor.id] = defaults;
          }
          return next;
        });
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [api, quoteId, selectedLines, includeAllVendors]);

  // Files + the export-control warning follow what is actually *selected*, not the
  // whole checklist — an unticked line is not being disclosed to anyone.
  const selectedLineRows = useMemo(
    () => allLines.filter((line) => selectedLines.includes(line.quote_item_id)),
    [allLines, selectedLines],
  );
  const allFiles = useMemo(
    () => selectedLineRows.flatMap((line) => line.files),
    [selectedLineRows],
  );
  const exportControlled = useMemo(
    () => selectedLineRows.some((line) => line.export_controlled),
    [selectedLineRows],
  );

  const toggle = (list: string[], id: string) =>
    list.includes(id) ? list.filter((x) => x !== id) : [...list, id];

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    const recipients: SendRecipient[] = selectedVendors.map((vendorId) => ({
      vendor_id: vendorId,
      vendor_contact_id: compose?.vendors.find((v) => v.id === vendorId)?.contact_id ?? undefined,
      part_file_ids: vendorFiles[vendorId] ?? [],
    }));
    api
      .sendBatch({
        quote_id: quoteId,
        quote_item_ids: selectedLines,
        recipients,
        need_by_date: needBy || null,
        message: message.trim() || null,
        costing_mode: costingMode || null,
      })
      .then((res) => onSent(res.rfqs.length))
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.message : String(e));
        setSubmitting(false);
      });
  };

  return (
    <div className="crm-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        ref={dialogRef}
        className="crm-modal crm-modal-wide"
        role="dialog"
        aria-modal="true"
        aria-label={t('vendorRfq.send_title')}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="crm-modal-title">{t('vendorRfq.send_title')}</h2>
        <form className="crm-form" onSubmit={submit}>
          <fieldset className="crm-fieldset">
            <legend>{t('vendorRfq.section.lines')}</legend>
            {allLines.map((line) => (
              <label key={line.quote_item_id} className="crm-check">
                <input
                  type="checkbox"
                  checked={selectedLines.includes(line.quote_item_id)}
                  onChange={() => setSelectedLines((prev) => toggle(prev, line.quote_item_id))}
                />
                <span>
                  {line.part_number ?? t('vendorRfq.unnamed_part')}
                  {line.revision ? ` · Rev ${line.revision}` : ''}
                  {line.outside_processes.length > 0
                    ? ` · ${line.outside_processes.join(', ')}`
                    : ''}
                  {line.quantities.length > 0 ? ` · ${line.quantities.join(' / ')}` : ''}
                </span>
              </label>
            ))}
          </fieldset>

          {exportControlled && (
            /* Informational, not a block: the human-vendor lane runs on the shop's
               existing supplier agreements (spec GDPR paragraph). The hard per-send
               gate belongs to the marketplace adapter (M6.7c). */
            <p className="crm-warning" role="status">
              {t('vendorRfq.export_controlled_warning')}
            </p>
          )}

          <fieldset className="crm-fieldset">
            <legend>{t('vendorRfq.section.vendors')}</legend>
            <label className="crm-check">
              <input
                type="checkbox"
                checked={includeAllVendors}
                onChange={(e) => setIncludeAllVendors(e.target.checked)}
              />
              <span>{t('vendorRfq.show_all_vendors')}</span>
            </label>
            {(compose?.vendors ?? []).map((vendor) => (
              <div key={vendor.id} className="crm-vendor-row">
                <label className="crm-check">
                  <input
                    type="checkbox"
                    checked={selectedVendors.includes(vendor.id)}
                    onChange={() => setSelectedVendors((prev) => toggle(prev, vendor.id))}
                  />
                  <span>
                    {vendor.name}
                    {vendor.is_new && (
                      <span className="crm-chip crm-chip-new">{t('vendorRfq.new_label')}</span>
                    )}
                    {vendor.contact_email ? ` · ${vendor.contact_email}` : ''}
                  </span>
                </label>
                {selectedVendors.includes(vendor.id) && allFiles.length > 0 && (
                  <div className="crm-vendor-files">
                    {allFiles.map((file) => (
                      <label key={`${vendor.id}-${file.id}`} className="crm-check">
                        <input
                          type="checkbox"
                          checked={(vendorFiles[vendor.id] ?? []).includes(file.id)}
                          onChange={() =>
                            setVendorFiles((prev) => ({
                              ...prev,
                              [vendor.id]: toggle(prev[vendor.id] ?? [], file.id),
                            }))
                          }
                        />
                        <span>
                          {file.filename}
                          {file.is_redacted && (
                            <span className="crm-chip">{t('vendorRfq.redacted_label')}</span>
                          )}
                        </span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {compose !== null && compose.vendors.length === 0 && (
              <p className="crm-empty">{t('vendorRfq.no_matching_vendors')}</p>
            )}
          </fieldset>

          <label className="crm-field">
            <span>{t('vendorRfq.field.need_by')}</span>
            <input type="date" value={needBy} onChange={(e) => setNeedBy(e.target.value)} />
          </label>
          <label className="crm-field">
            <span>{t('vendorRfq.field.message')}</span>
            <textarea value={message} rows={3} onChange={(e) => setMessage(e.target.value)} />
          </label>
          <label className="crm-field">
            <span>{t('vendorRfq.field.costing_mode')}</span>
            <select
              value={costingMode}
              onChange={(e) => setCostingMode(e.target.value as CostingMode | '')}
            >
              <option value="">{t('vendorRfq.costing_mode.unchanged')}</option>
              <option value="make">{t('vendorRfq.costing_mode.make')}</option>
              <option value="buy">{t('vendorRfq.costing_mode.buy')}</option>
            </select>
          </label>

          {error && (
            <p className="crm-error" role="alert">
              {error}
            </p>
          )}

          <div className="crm-modal-actions">
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              {t('vendorRfq.actions.cancel')}
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || selectedLines.length === 0 || selectedVendors.length === 0}
            >
              {t('vendorRfq.actions.send', { count: selectedVendors.length })}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
