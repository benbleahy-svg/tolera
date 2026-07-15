/**
 * Settings → User Profile → Email Connection (M3.5, spec #email-connectivity):
 * one-click "Connect Gmail" / "Connect Outlook" (OAuth popup → provider), a
 * manual SMTP/IMAP form, connection status (from-address, last synced), set
 * primary, "Test connection" (sends to the user's own address) and disconnect.
 * Gmail ships behind Google's pending-verification warning
 * (DECISIONS.md 2026-06-14) — the hint below the button says so.
 */

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { useEmailApi } from './api';
import type { EmailConnection } from './types';

const EMPTY_FORM = {
  from_address: '',
  from_name: '',
  smtp_host: '',
  smtp_port: '587',
  imap_host: '',
  imap_port: '993',
  username: '',
  password: '',
};

function typeLabel(type: EmailConnection['connection_type']): string {
  if (type === 'gmail') return 'Gmail';
  if (type === 'outlook') return 'Outlook / Microsoft 365';
  return 'SMTP/IMAP';
}

export function EmailConnectionPage() {
  const { t, i18n } = useTranslation();
  const api = useEmailApi();
  const [connections, setConnections] = useState<EmailConnection[] | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [showForm, setShowForm] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .listConnections()
      .then(setConnections)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  const fail = (e: unknown) => {
    if (e instanceof ApiError && e.code === 'oauth_not_configured') {
      setError(t('email.oauth_not_configured'));
    } else {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const startOauth = (provider: 'gmail' | 'outlook') => {
    setError(null);
    api
      .oauthStart(provider)
      .then(({ authorize_url }) => window.location.assign(authorize_url))
      .catch(fail);
  };

  const submitSmtp = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    api
      .connectSmtp({
        from_address: form.from_address,
        from_name: form.from_name || null,
        smtp_host: form.smtp_host,
        smtp_port: Number(form.smtp_port) || 587,
        imap_host: form.imap_host,
        imap_port: Number(form.imap_port) || 993,
        username: form.username,
        password: form.password,
      })
      .then(() => {
        setForm(EMPTY_FORM);
        setShowForm(false);
        setNotice(t('email.connected'));
        load();
      })
      .catch(fail);
  };

  const runTest = (id: string) => {
    setError(null);
    setNotice(null);
    api
      .testConnection(id)
      .then(() => setNotice(t('email.test_sent')))
      .catch(fail);
  };

  const formatSynced = (value: string | null) =>
    value ? new Date(value).toLocaleString(i18n.language) : t('email.never_synced');

  const field = (key: keyof typeof EMPTY_FORM, labelKey: string, type = 'text') => (
    <label className="form-field">
      <span>{t(labelKey)}</span>
      <input
        type={type}
        value={form[key]}
        required={key !== 'from_name'}
        onChange={(event) => setForm((f) => ({ ...f, [key]: event.target.value }))}
      />
    </label>
  );

  return (
    <div className="page email-settings">
      <header className="page-header">
        <h1>{t('email.title')}</h1>
        <p className="page-subtitle">{t('email.subtitle')}</p>
      </header>

      {notice && <div className="banner success">{notice}</div>}
      {error && (
        <div className="banner error" role="alert">
          {error}
        </div>
      )}

      <section className="panel">
        <h2>{t('email.connect_heading')}</h2>
        <div className="connect-buttons">
          <button type="button" onClick={() => startOauth('gmail')}>
            {t('email.connect_gmail')}
          </button>
          <button type="button" onClick={() => startOauth('outlook')}>
            {t('email.connect_outlook')}
          </button>
          <button type="button" onClick={() => setShowForm((v) => !v)}>
            {t('email.manual_smtp')}
          </button>
        </div>
        {/* DECISIONS.md 2026-06-14: pending Google verification warning. */}
        <p className="hint">{t('email.gmail_pending_review')}</p>

        {showForm && (
          <form className="smtp-form" onSubmit={submitSmtp}>
            {field('from_address', 'email.from_address', 'email')}
            {field('from_name', 'email.from_name')}
            {field('smtp_host', 'email.smtp_host')}
            {field('smtp_port', 'email.smtp_port', 'number')}
            {field('imap_host', 'email.imap_host')}
            {field('imap_port', 'email.imap_port', 'number')}
            {field('username', 'email.username')}
            {field('password', 'email.password', 'password')}
            <button type="submit">{t('email.save_connection')}</button>
          </form>
        )}
      </section>

      <section className="panel">
        <h2>{t('email.connections_heading')}</h2>
        {connections === null ? (
          <p>{t('common.loading')}</p>
        ) : connections.length === 0 ? (
          <p>{t('email.none_connected')}</p>
        ) : (
          <ul className="connection-list">
            {connections.map((connection) => (
              <li key={connection.id} className="connection-row">
                <div className="connection-id">
                  <strong>{connection.from_address}</strong>
                  <span className="connection-type">{typeLabel(connection.connection_type)}</span>
                  {connection.is_primary && (
                    <span className="badge primary">{t('email.primary')}</span>
                  )}
                </div>
                <div className="connection-status">
                  <span>
                    {t('email.last_synced')}: {formatSynced(connection.last_synced_at)}
                  </span>
                  {connection.last_sync_error && (
                    <span className="sync-error">
                      {t('email.sync_error')}: {connection.last_sync_error}
                    </span>
                  )}
                </div>
                <div className="connection-actions">
                  {!connection.is_primary && (
                    <button
                      type="button"
                      onClick={() => {
                        api.setPrimary(connection.id).then(load).catch(fail);
                      }}
                    >
                      {t('email.set_primary')}
                    </button>
                  )}
                  <button type="button" onClick={() => runTest(connection.id)}>
                    {t('email.test_connection')}
                  </button>
                  <button
                    type="button"
                    className="danger"
                    onClick={() => {
                      api.disconnect(connection.id).then(load).catch(fail);
                    }}
                  >
                    {t('email.disconnect')}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
