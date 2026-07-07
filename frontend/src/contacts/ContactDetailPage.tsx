/**
 * Contact detail — `/contacts/:accountId/contacts/:contactId` (spec #contacts
 * contact detail). Editable contact fields + archive/restore, with a breadcrumb
 * back to the parent account.
 */

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { errorMessage } from '../api/errors';
import { useHasPermission } from '../session/session';
import { contactDisplayName } from './format';
import { type Contact, useCrmApi } from './api';

export function ContactDetailPage() {
  const { t } = useTranslation();
  const api = useCrmApi();
  const { accountId: routeAccountId = '', contactId = '' } = useParams();
  const canEdit = useHasPermission('quote_edit');
  const canArchive = useHasPermission('quote_delete');

  const [contact, setContact] = useState<Contact | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [role, setRole] = useState('');
  const [phone, setPhone] = useState('');
  const loadSeq = useRef(0);

  const seed = useCallback((c: Contact) => {
    setContact(c);
    setEmail(c.email);
    setFirstName(c.first_name ?? '');
    setLastName(c.last_name ?? '');
    setRole(c.role ?? '');
    setPhone(c.phone ?? '');
  }, []);

  const reportError = useCallback((e: unknown) => setError(errorMessage(e, t)), [t]);

  useEffect(() => {
    // Clear the old contact and ignore an out-of-order response, so navigating
    // between contacts can't leave stale data in the edit form.
    const seq = ++loadSeq.current;
    setError(null);
    setContact(null);
    api
      .getContact(contactId)
      .then((next) => {
        if (seq === loadSeq.current) seed(next);
      })
      .catch((e: unknown) => {
        if (seq === loadSeq.current) reportError(e);
      });
  }, [api, contactId, seed, reportError]);

  const save = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    // Pin to the current load so a save that resolves after navigating to another
    // contact can't seed this contact's data into the new view.
    const seq = loadSeq.current;
    api
      .updateContact(contactId, {
        email: email.trim(),
        first_name: firstName.trim() || null,
        last_name: lastName.trim() || null,
        role: role.trim() || null,
        phone: phone.trim() || null,
      })
      .then((next) => {
        // Update the record (title, archived chip) but do NOT re-seed the form:
        // re-seeding would silently revert anything typed while the save was
        // in flight.
        if (seq === loadSeq.current) setContact(next);
      })
      .catch((e: unknown) => {
        if (seq === loadSeq.current) reportError(e);
      });
  };

  const toggleArchive = () => {
    if (!contact) return;
    setError(null);
    const seq = loadSeq.current;
    const action = contact.archived ? api.restoreContact : api.archiveContact;
    action(contactId)
      .then((next) => {
        // Same as save: update the record, keep unsaved form edits intact.
        if (seq === loadSeq.current) setContact(next);
      })
      .catch((e: unknown) => {
        if (seq === loadSeq.current) reportError(e);
      });
  };

  if (!contact) {
    return (
      <section className="page">
        {error ? (
          <p className="crm-error" role="alert">
            {error}
          </p>
        ) : (
          <p className="page-empty">{t('contacts.loading')}</p>
        )}
      </section>
    );
  }

  return (
    <section className="page">
      {/* Trust the contact's own account over a possibly-stale route param. */}
      <Link className="crm-back" to={`/contacts/${contact.account_id ?? routeAccountId}`}>
        ← {t('contacts.back_to_account')}
      </Link>
      <div className="crm-header">
        <h1 className="page-title">
          {contactDisplayName(contact)}
          {contact.archived && (
            <span className="crm-chip crm-chip-archived">{t('contacts.status.archived')}</span>
          )}
        </h1>
        {canArchive && (
          <button type="button" className="btn btn-ghost" onClick={toggleArchive}>
            {contact.archived ? t('contacts.actions.restore') : t('contacts.actions.archive')}
          </button>
        )}
      </div>

      {error && (
        <p className="crm-error" role="alert">
          {error}
        </p>
      )}

      <form className="crm-form crm-form-grid" onSubmit={save}>
        <label className="crm-field">
          <span>{t('contacts.field.email')}</span>
          <input value={email} disabled={!canEdit} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="crm-field">
          <span>{t('contacts.field.role')}</span>
          <input value={role} disabled={!canEdit} onChange={(e) => setRole(e.target.value)} />
        </label>
        <label className="crm-field">
          <span>{t('contacts.field.first_name')}</span>
          <input
            value={firstName}
            disabled={!canEdit}
            onChange={(e) => setFirstName(e.target.value)}
          />
        </label>
        <label className="crm-field">
          <span>{t('contacts.field.last_name')}</span>
          <input value={lastName} disabled={!canEdit} onChange={(e) => setLastName(e.target.value)} />
        </label>
        <label className="crm-field">
          <span>{t('contacts.field.phone')}</span>
          <input value={phone} disabled={!canEdit} onChange={(e) => setPhone(e.target.value)} />
        </label>
        {canEdit && (
          <div className="crm-form-actions">
            <button type="submit" className="btn btn-primary">
              {t('contacts.actions.save')}
            </button>
          </div>
        )}
      </form>
    </section>
  );
}
