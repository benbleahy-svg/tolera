/**
 * Create Account modal (spec #contacts Create-Account modal): Company Name + an
 * optional primary contact (name + email). Posts to `/api/accounts`, surfacing
 * the backend envelope message (e.g. a duplicate-email 409) inline.
 */

import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
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
        setError(e instanceof ApiError ? e.message : String(e));
        setSubmitting(false);
      });
  };

  return (
    <div className="crm-modal-backdrop" role="presentation" onClick={onClose}>
      <div
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
