/**
 * Accounts list — the `/contacts` destination (spec #contacts). Lists the active
 * org's accounts with search + a show-archived toggle, and a Create Account modal
 * (gated on `quote_edit`). Derived columns (revenue, quotes sent) arrive with
 * quotes/orders in later milestones; M1.1 shows the identity columns only.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { errorMessage } from '../api/errors';
import { useHasPermission } from '../session/session';
import { CreateAccountModal } from './CreateAccountModal';
import { type Account, useCrmApi } from './api';

export function ContactsPage() {
  const { t } = useTranslation();
  const api = useCrmApi();
  const canEdit = useHasPermission('quote_edit');

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [q, setQ] = useState('');
  const [includeArchived, setIncludeArchived] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const requestSeq = useRef(0);

  const load = useCallback(() => {
    const seq = ++requestSeq.current;
    setError(null);
    api
      .listAccounts({ q: q.trim() || undefined, includeArchived })
      .then((next) => {
        // Ignore a slow earlier request that resolves after a newer one.
        if (seq === requestSeq.current) setAccounts(next);
      })
      .catch((e: unknown) => {
        if (seq === requestSeq.current) {
          setError(errorMessage(e, t));
        }
      });
  }, [api, q, includeArchived, t]);

  const firstLoad = useRef(true);
  useEffect(() => {
    // Debounce keystrokes, but fire the mount load immediately — the initial
    // list shouldn't wait 200 ms for a debounce it doesn't need.
    if (firstLoad.current) {
      firstLoad.current = false;
      load();
      return;
    }
    const handle = setTimeout(load, 200);
    return () => clearTimeout(handle);
  }, [load]);

  return (
    <section className="page">
      <div className="crm-header">
        <h1 className="page-title">{t('nav.contacts')}</h1>
        {canEdit && (
          <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
            {t('contacts.create_account')}
          </button>
        )}
      </div>

      <div className="crm-toolbar">
        <input
          className="crm-search"
          type="search"
          value={q}
          placeholder={t('contacts.search_placeholder')}
          aria-label={t('contacts.search_placeholder')}
          onChange={(e) => setQ(e.target.value)}
        />
        <label className="crm-toggle">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
          />
          {t('contacts.show_archived')}
        </label>
      </div>

      {error && (
        <p className="crm-error" role="alert">
          {error}
        </p>
      )}

      {accounts.length === 0 ? (
        <p className="page-empty">{t('contacts.empty')}</p>
      ) : (
        <table className="crm-table">
          <thead>
            <tr>
              <th>{t('contacts.col.name')}</th>
              <th>{t('contacts.col.type')}</th>
              <th>{t('contacts.col.email')}</th>
              <th>{t('contacts.col.status')}</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((account) => (
              <tr key={account.id}>
                <td>
                  <Link to={`/contacts/${account.id}`}>{account.name}</Link>
                </td>
                <td>{t(`contacts.type.${account.type}`)}</td>
                <td>{account.email ?? '—'}</td>
                <td>
                  {account.archived ? (
                    <span className="crm-chip crm-chip-archived">{t('contacts.status.archived')}</span>
                  ) : (
                    <span className="crm-chip">{t('contacts.status.active')}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {creating && (
        <CreateAccountModal
          onClose={() => setCreating(false)}
          onCreated={() => {
            setCreating(false);
            load();
          }}
        />
      )}
    </section>
  );
}
