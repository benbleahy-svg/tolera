/**
 * Account detail — `/contacts/:accountId` (spec #contacts account detail). Shows
 * the account's editable fields, an archive/restore control (gated `quote_delete`),
 * and its Contacts (add gated `quote_edit`, each linking to the contact detail).
 * The spec's Quotes/Settings tabs depend on later milestones and are out of M1.1.
 */

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { useHasPermission } from '../session/session';
import { contactDisplayName } from './format';
import { type Account, type Contact, useCrmApi } from './api';

export function AccountDetailPage() {
  const { t } = useTranslation();
  const api = useCrmApi();
  const { accountId = '' } = useParams();
  const canEdit = useHasPermission('quote_edit');
  const canArchive = useHasPermission('quote_delete');

  const [account, setAccount] = useState<Account | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Editable account fields (seeded from the loaded account).
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [website, setWebsite] = useState('');
  const [notes, setNotes] = useState('');

  const seed = useCallback((acc: Account) => {
    setAccount(acc);
    setName(acc.name);
    setEmail(acc.email ?? '');
    setPhone(acc.phone ?? '');
    setWebsite(acc.website ?? '');
    setNotes(acc.notes ?? '');
  }, []);

  const reportError = useCallback(
    (e: unknown) => setError(e instanceof ApiError ? e.message : String(e)),
    [],
  );

  const loadContacts = useCallback(() => {
    api.listAccountContacts(accountId).then(setContacts).catch(reportError);
  }, [api, accountId, reportError]);

  useEffect(() => {
    setError(null);
    api.getAccount(accountId).then(seed).catch(reportError);
    loadContacts();
  }, [api, accountId, seed, reportError, loadContacts]);

  const saveAccount = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    api
      .updateAccount(accountId, {
        name: name.trim(),
        email: email.trim() || null,
        phone: phone.trim() || null,
        website: website.trim() || null,
        notes: notes.trim() || null,
      })
      .then(seed)
      .catch(reportError);
  };

  const toggleArchive = () => {
    if (!account) return;
    setError(null);
    const action = account.archived ? api.restoreAccount : api.archiveAccount;
    action(accountId).then(seed).catch(reportError);
  };

  if (!account) {
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
      <Link className="crm-back" to="/contacts">
        ← {t('nav.contacts')}
      </Link>
      <div className="crm-header">
        <h1 className="page-title">
          {account.name}
          {account.archived && (
            <span className="crm-chip crm-chip-archived">{t('contacts.status.archived')}</span>
          )}
        </h1>
        {canArchive && (
          <button type="button" className="btn btn-ghost" onClick={toggleArchive}>
            {account.archived ? t('contacts.actions.restore') : t('contacts.actions.archive')}
          </button>
        )}
      </div>

      {error && (
        <p className="crm-error" role="alert">
          {error}
        </p>
      )}

      <form className="crm-form crm-form-grid" onSubmit={saveAccount}>
        <label className="crm-field">
          <span>{t('contacts.field.company_name')}</span>
          <input value={name} disabled={!canEdit} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="crm-field">
          <span>{t('contacts.field.email')}</span>
          <input value={email} disabled={!canEdit} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="crm-field">
          <span>{t('contacts.field.phone')}</span>
          <input value={phone} disabled={!canEdit} onChange={(e) => setPhone(e.target.value)} />
        </label>
        <label className="crm-field">
          <span>{t('contacts.field.website')}</span>
          <input value={website} disabled={!canEdit} onChange={(e) => setWebsite(e.target.value)} />
        </label>
        <label className="crm-field crm-field-wide">
          <span>{t('contacts.field.notes')}</span>
          <textarea value={notes} disabled={!canEdit} onChange={(e) => setNotes(e.target.value)} />
        </label>
        {canEdit && (
          <div className="crm-form-actions">
            <button type="submit" className="btn btn-primary">
              {t('contacts.actions.save')}
            </button>
          </div>
        )}
      </form>

      <div className="crm-section">
        <h2 className="crm-section-title">{t('contacts.contacts_title')}</h2>
        {contacts.length === 0 ? (
          <p className="page-empty">{t('contacts.no_contacts')}</p>
        ) : (
          <ul className="crm-list">
            {contacts.map((contact) => (
              <li key={contact.id} className="crm-list-row">
                <Link to={`/contacts/${accountId}/contacts/${contact.id}`}>
                  {contactDisplayName(contact)}
                </Link>
                <span className="crm-list-meta">{contact.email}</span>
              </li>
            ))}
          </ul>
        )}
        {canEdit && <AddContactForm accountId={accountId} onAdded={loadContacts} />}
      </div>
    </section>
  );
}

function AddContactForm({ accountId, onAdded }: { accountId: string; onAdded: () => void }) {
  const { t } = useTranslation();
  const api = useCrmApi();
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    api
      .createContact(accountId, {
        email: email.trim(),
        first_name: firstName.trim() || null,
        last_name: lastName.trim() || null,
      })
      .then(() => {
        setEmail('');
        setFirstName('');
        setLastName('');
        onAdded();
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  };

  return (
    <form className="crm-add-contact" onSubmit={submit}>
      <input
        type="email"
        required
        value={email}
        placeholder={t('contacts.field.email')}
        aria-label={t('contacts.field.email')}
        onChange={(e) => setEmail(e.target.value)}
      />
      <input
        value={firstName}
        placeholder={t('contacts.field.first_name')}
        aria-label={t('contacts.field.first_name')}
        onChange={(e) => setFirstName(e.target.value)}
      />
      <input
        value={lastName}
        placeholder={t('contacts.field.last_name')}
        aria-label={t('contacts.field.last_name')}
        onChange={(e) => setLastName(e.target.value)}
      />
      <button type="submit" className="btn btn-primary" disabled={!email.trim()}>
        {t('contacts.add_contact')}
      </button>
      {error && (
        <p className="crm-error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
