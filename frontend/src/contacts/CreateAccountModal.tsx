/**
 * Create Account modal (spec #contacts Create-Account modal): Company Name + an
 * optional primary contact (name + email). Posts to `/api/accounts`, surfacing
 * the backend envelope message (e.g. a duplicate-email 409) inline.
 */

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { errorMessage } from '../api/errors';
import { type AccountCreate, useCrmApi } from './api';

export function CreateAccountModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation();
  const api = useCrmApi();
  const [name, setName] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [contactFirstName, setContactFirstName] = useState('');
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
      // Exclude disabled controls: the submit button is disabled until the name
      // is filled, and a disabled `last` can never be activeElement, so the
      // Tab-on-last wrap check would never fire and focus would escape.
      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), ' +
          'select:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
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
    const body: AccountCreate = { name: name.trim() };
    if (contactEmail.trim()) {
      body.primary_contact = {
        email: contactEmail.trim(),
        first_name: contactFirstName.trim() || null,
      };
    }
    api
      .createAccount(body)
      .then(onCreated)
      .catch((e: unknown) => {
        setError(errorMessage(e, t));
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
        aria-label={t('contacts.create_account_title')}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="crm-modal-title">{t('contacts.create_account_title')}</h2>
        <form className="crm-form" onSubmit={submit}>
          <label className="crm-field">
            <span>{t('contacts.field.company_name')}</span>
            <input value={name} required onChange={(e) => setName(e.target.value)} autoFocus />
          </label>
          <label className="crm-field">
            <span>{t('contacts.field.contact_email')}</span>
            <input
              type="email"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
            />
          </label>
          <label className="crm-field">
            <span>{t('contacts.field.first_name')}</span>
            <input value={contactFirstName} onChange={(e) => setContactFirstName(e.target.value)} />
          </label>

          {error && (
            <p className="crm-error" role="alert">
              {error}
            </p>
          )}

          <div className="crm-modal-actions">
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              {t('contacts.actions.cancel')}
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting || !name.trim()}>
              {t('contacts.actions.create')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
