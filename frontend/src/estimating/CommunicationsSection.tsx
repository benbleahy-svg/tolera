/**
 * The quote's unified communications timeline (M3.5, spec #email-connectivity):
 * every email on the quote's thread, both directions, oldest first — plus a
 * minimal send box (the full composer with templates + quote PDF is M5).
 * Sending needs a connected mailbox; without one the banner points to
 * Settings → Email Connection (the fallback platform-send path is M5).
 */

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ApiError } from '../api/client';
import { useEmailApi } from '../settings/api';
import type { EmailMessage } from '../settings/types';

export function CommunicationsSection({
  quoteId,
  canSend,
}: {
  quoteId: string;
  canSend: boolean;
}) {
  const { t, i18n } = useTranslation();
  const api = useEmailApi();
  const [messages, setMessages] = useState<EmailMessage[] | null>(null);
  const [composing, setComposing] = useState(false);
  const [to, setTo] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [noConnection, setNoConnection] = useState(false);

  const load = useCallback(() => {
    api
      .getQuoteEmails(quoteId)
      .then(setMessages)
      .catch(() => setMessages([]));
  }, [api, quoteId]);

  useEffect(() => {
    load();
  }, [load]);

  const send = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setNoConnection(false);
    api
      .sendQuoteEmail(quoteId, {
        to: to
          .split(',')
          .map((addr) => addr.trim())
          .filter(Boolean),
        subject,
        body_text: body,
      })
      .then(() => {
        setComposing(false);
        setTo('');
        setSubject('');
        setBody('');
        load();
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.code === 'no_email_connection') {
          setNoConnection(true);
        } else {
          setError(e instanceof Error ? e.message : String(e));
        }
      });
  };

  const stamp = (message: EmailMessage) => {
    const value = message.sent_at ?? message.created_at;
    return new Date(value).toLocaleString(i18n.language);
  };

  return (
    <section className="panel communications" aria-label={t('email.timeline_heading')}>
      <div className="panel-header">
        <h2>{t('email.timeline_heading')}</h2>
        {canSend && (
          <button type="button" onClick={() => setComposing((v) => !v)}>
            {t('email.compose')}
          </button>
        )}
      </div>

      {noConnection && (
        <div className="banner warning" role="alert">
          {t('email.no_connection')} <Link to="/settings/email">{t('email.go_connect')}</Link>
        </div>
      )}
      {error && (
        <div className="banner error" role="alert">
          {error}
        </div>
      )}

      {composing && (
        <form className="compose-form" onSubmit={send}>
          <label className="form-field">
            <span>{t('email.to')}</span>
            <input value={to} required onChange={(event) => setTo(event.target.value)} />
          </label>
          <label className="form-field">
            <span>{t('email.subject')}</span>
            <input
              value={subject}
              required
              onChange={(event) => setSubject(event.target.value)}
            />
          </label>
          <label className="form-field">
            <span>{t('email.body')}</span>
            <textarea
              value={body}
              required
              rows={5}
              onChange={(event) => setBody(event.target.value)}
            />
          </label>
          <button type="submit">{t('email.send')}</button>
        </form>
      )}

      {messages === null ? (
        <p>{t('common.loading')}</p>
      ) : messages.length === 0 ? (
        <p className="empty">{t('email.no_messages')}</p>
      ) : (
        <ol className="timeline">
          {messages.map((message) => (
            <li
              key={message.id}
              className={`timeline-entry ${message.direction}`}
              data-direction={message.direction}
            >
              <div className="entry-meta">
                <span className="direction-badge">
                  {message.direction === 'outbound'
                    ? t('email.outbound')
                    : t('email.inbound')}
                </span>
                <span className="entry-from">{message.from_address}</span>
                <time>{stamp(message)}</time>
              </div>
              {message.subject && <div className="entry-subject">{message.subject}</div>}
              {message.body_text && <p className="entry-body">{message.body_text}</p>}
              {message.attachments.length > 0 && (
                <ul className="entry-attachments">
                  {message.attachments.map((attachment) => (
                    <li key={attachment.storage_key}>
                      📎 {attachment.filename} ({Math.ceil(attachment.size_bytes / 1024)} KB)
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
