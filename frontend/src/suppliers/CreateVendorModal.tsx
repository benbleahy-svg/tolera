/**
 * ADD VENDOR modal (spec #vendor-rfq, Supplier Directory toolbar): company
 * identity + capability chips + an optional first quoting contact. Posts to
 * `/api/vendors`, surfacing the backend envelope message inline.
 *
 * Capability tags are typed comma-separated and normalized server-side, matching
 * the "tag chips" the directory filters on.
 */

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { type VendorCreate, useVendorsApi } from './api';
import { splitTagInput } from './tags';

export function CreateVendorModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation();
  const api = useVendorsApi();
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [vatId, setVatId] = useState('');
  const [processes, setProcesses] = useState('');
  const [materials, setMaterials] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [contactName, setContactName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

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

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    const body: VendorCreate = {
      name: name.trim(),
      address: address.trim() || null,
      vat_id: vatId.trim() || null,
      capabilities: {
        processes: splitTagInput(processes),
        materials: splitTagInput(materials),
      },
    };
    if (contactEmail.trim()) {
      body.primary_contact = {
        email: contactEmail.trim(),
        name: contactName.trim() || null,
        is_primary: true,
      };
    }
    api
      .createVendor(body)
      .then(onCreated)
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.message : String(e));
        setSubmitting(false);
      });
  };

  return (
    <div className="crm-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        ref={dialogRef}
        className="crm-modal"
        role="dialog"
        aria-modal="true"
        aria-label={t('suppliers.create_title')}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="crm-modal-title">{t('suppliers.create_title')}</h2>
        <form className="crm-form" onSubmit={submit}>
          <label className="crm-field">
            <span>{t('suppliers.field.name')}</span>
            <input value={name} required onChange={(e) => setName(e.target.value)} autoFocus />
          </label>
          <label className="crm-field">
            <span>{t('suppliers.field.address')}</span>
            <textarea value={address} rows={2} onChange={(e) => setAddress(e.target.value)} />
          </label>
          <label className="crm-field">
            <span>{t('suppliers.field.vat_id')}</span>
            <input value={vatId} onChange={(e) => setVatId(e.target.value)} />
          </label>
          <label className="crm-field">
            <span>{t('suppliers.field.processes')}</span>
            <input
              value={processes}
              placeholder={t('suppliers.tag_placeholder')}
              onChange={(e) => setProcesses(e.target.value)}
            />
          </label>
          <label className="crm-field">
            <span>{t('suppliers.field.materials')}</span>
            <input
              value={materials}
              placeholder={t('suppliers.tag_placeholder')}
              onChange={(e) => setMaterials(e.target.value)}
            />
          </label>
          <label className="crm-field">
            <span>{t('suppliers.field.contact_email')}</span>
            {/* A contact is only submitted when it has an address (the RFQ has to
                reach someone), so a name typed without one would be silently
                dropped. Requiring the address once a name is present lets native
                validation catch the half-filled contact at submit time. */}
            <input
              type="email"
              value={contactEmail}
              required={contactName.trim() !== ''}
              onChange={(e) => setContactEmail(e.target.value)}
            />
          </label>
          <label className="crm-field">
            <span>{t('suppliers.field.contact_name')}</span>
            <input value={contactName} onChange={(e) => setContactName(e.target.value)} />
          </label>

          {error && (
            <p className="crm-error" role="alert">
              {error}
            </p>
          )}

          <div className="crm-modal-actions">
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              {t('suppliers.actions.cancel')}
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting || !name.trim()}>
              {t('suppliers.actions.create')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
