/**
 * Send-quote composer (M5.5, spec #email-templates, DemoK/12) — "Wer erhält
 * dieses Angebot?". To/CC/BCC recipient rows with add + remove, a quote-send
 * template picker that fills Subject + Body, a rich-text body editor (execCommand
 * toolbar) whose HTML is the sent `body_html`, an "attach quote PDF" toggle, and
 * VORSCHAU (resolves merge fields, no send) + ANGEBOT SENDEN. A missing mailbox
 * (`no_email_connection`) surfaces a banner linking to Settings → Email Connection.
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ApiError } from '../api/client';
import { useEmailApi, useEmailTemplatesApi } from '../settings/api';
import type { EmailTemplate, SendQuoteBody, SendQuotePreview } from '../settings/types';
import { CustomerBriefCard } from './CustomerBriefCard';

type RecipientType = 'to' | 'cc' | 'bcc';

interface Recipient {
  type: RecipientType;
  email: string;
}

const RECIPIENT_TYPES: RecipientType[] = ['to', 'cc', 'bcc'];

interface Props {
  quoteId: string;
  onClose: () => void;
  onSent: () => void;
}

export function SendQuoteComposer({ quoteId, onClose, onSent }: Props) {
  const { t } = useTranslation();
  const emailApi = useEmailApi();
  const templatesApi = useEmailTemplatesApi();

  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [templateId, setTemplateId] = useState('');
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [draftType, setDraftType] = useState<RecipientType>('to');
  const [draftEmail, setDraftEmail] = useState('');
  const [subject, setSubject] = useState('');
  const [includePdf, setIncludePdf] = useState(true);
  const [preview, setPreview] = useState<SendQuotePreview | null>(null);
  const [sending, setSending] = useState(false);
  const [noConnection, setNoConnection] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    templatesApi
      .list('quote_send')
      .then((list) => {
        setTemplates(list);
        // Pre-select the org default so the composer opens ready to send.
        const def = list.find((tpl) => tpl.is_default);
        if (def) {
          setTemplateId(def.id);
          setSubject(def.subject);
          if (bodyRef.current) bodyRef.current.innerHTML = def.body;
        }
      })
      .catch(() => setTemplates([]));
  }, [templatesApi]);

  const pickTemplate = (id: string) => {
    setTemplateId(id);
    const tpl = templates.find((x) => x.id === id);
    if (!tpl) return;
    setSubject(tpl.subject);
    if (bodyRef.current) bodyRef.current.innerHTML = tpl.body;
  };

  const addRecipient = () => {
    const email = draftEmail.trim();
    if (!email) return;
    setRecipients((prev) => [...prev, { type: draftType, email }]);
    setDraftEmail('');
  };

  const removeRecipient = (index: number) =>
    setRecipients((prev) => prev.filter((_, i) => i !== index));

  const exec = (command: string) => {
    bodyRef.current?.focus();
    document.execCommand(command, false);
  };

  const insertLink = () => {
    const url = window.prompt(t('sendComposer.link_prompt'));
    if (!url) return;
    bodyRef.current?.focus();
    document.execCommand('createLink', false, url);
  };

  // At least one To recipient is required before preview or send (a quote with no
  // primary recipient has nobody to receive the portal link).
  const hasTo = recipients.some((r) => r.type === 'to');

  const buildBody = (): SendQuoteBody => ({
    to: recipients.filter((r) => r.type === 'to').map((r) => r.email),
    cc: recipients.filter((r) => r.type === 'cc').map((r) => r.email),
    bcc: recipients.filter((r) => r.type === 'bcc').map((r) => r.email),
    template_id: templateId || null,
    subject,
    body_html: bodyRef.current?.innerHTML ?? '',
    include_pdf: includePdf,
  });

  const fail = (e: unknown) => {
    if (e instanceof ApiError && e.code === 'no_email_connection') {
      setNoConnection(true);
    } else {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const runPreview = () => {
    if (!hasTo) return;
    setError(null);
    setNoConnection(false);
    emailApi.previewQuoteSend(quoteId, buildBody()).then(setPreview).catch(fail);
  };

  const send = () => {
    if (!hasTo) return;
    setError(null);
    setNoConnection(false);
    setSending(true); // a double-click must not send two real emails
    emailApi
      .sendQuote(quoteId, buildBody())
      .then(() => {
        onSent();
        onClose();
      })
      .catch(fail)
      .finally(() => setSending(false));
  };

  return (
    <div className="est-modal-backdrop" role="dialog" aria-label={t('sendComposer.title')}>
      <div className="est-modal send-composer">
        <h3>{t('sendComposer.title')}</h3>

        {noConnection && (
          <div className="banner warning" role="alert">
            {t('email.no_connection')}{' '}
            <Link to="/settings/email">{t('email.go_connect')}</Link>
          </div>
        )}
        {error && (
          <div className="banner error" role="alert">
            {error}
          </div>
        )}

        {/* AI Feature 5 (M5.10): "About this customer" brief, above To/CC/BCC. */}
        <CustomerBriefCard quoteId={quoteId} />

        <ul className="recipient-list">
          {recipients.map((r, i) => (
            <li key={`${r.type}-${r.email}-${i}`} className="recipient-row">
              <span className="recipient-type">{t(`sendComposer.type.${r.type}`)}</span>
              <span className="recipient-email">{r.email}</span>
              <button
                type="button"
                className="recipient-remove"
                aria-label={t('sendComposer.remove_recipient')}
                onClick={() => removeRecipient(i)}
              >
                🗑
              </button>
            </li>
          ))}
        </ul>
        <div className="recipient-add">
          <select
            aria-label={t('sendComposer.recipient_type')}
            value={draftType}
            onChange={(e) => setDraftType(e.target.value as RecipientType)}
          >
            {RECIPIENT_TYPES.map((type) => (
              <option key={type} value={type}>
                {t(`sendComposer.type.${type}`)}
              </option>
            ))}
          </select>
          <input
            type="email"
            placeholder={t('sendComposer.recipient_placeholder')}
            aria-label={t('sendComposer.recipient_email')}
            value={draftEmail}
            onChange={(e) => setDraftEmail(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addRecipient();
              }
            }}
          />
          <button type="button" onClick={addRecipient}>
            {t('common.add')}
          </button>
        </div>

        <label className="form-field">
          <span>{t('sendComposer.select_template')}</span>
          <select value={templateId} onChange={(e) => pickTemplate(e.target.value)}>
            <option value="">{t('sendComposer.no_template')}</option>
            {templates.map((tpl) => (
              <option key={tpl.id} value={tpl.id}>
                {tpl.name}
              </option>
            ))}
          </select>
        </label>

        <label className="form-field">
          <span>{t('sendComposer.subject')}</span>
          <input value={subject} onChange={(e) => setSubject(e.target.value)} />
        </label>

        <div className="body-toolbar" role="toolbar" aria-label={t('sendComposer.formatting')}>
          <button type="button" aria-label={t('sendComposer.bold')} onClick={() => exec('bold')}>
            <strong>B</strong>
          </button>
          <button type="button" aria-label={t('sendComposer.italic')} onClick={() => exec('italic')}>
            <em>I</em>
          </button>
          <button
            type="button"
            aria-label={t('sendComposer.underline')}
            onClick={() => exec('underline')}
          >
            <u>U</u>
          </button>
          <button
            type="button"
            aria-label={t('sendComposer.bullet_list')}
            onClick={() => exec('insertUnorderedList')}
          >
            ☰
          </button>
          <button type="button" aria-label={t('sendComposer.link')} onClick={insertLink}>
            🔗
          </button>
        </div>
        <div
          ref={bodyRef}
          className="body-editor"
          contentEditable
          role="textbox"
          aria-multiline="true"
          aria-label={t('sendComposer.body')}
          suppressContentEditableWarning
        />

        <label className="form-check">
          <input
            type="checkbox"
            checked={includePdf}
            onChange={(e) => setIncludePdf(e.target.checked)}
          />
          <span>{t('sendComposer.attach_pdf')}</span>
        </label>

        {preview && (
          <div className="send-preview" aria-label={t('sendComposer.preview_heading')}>
            <h4>{t('sendComposer.preview_heading')}</h4>
            <p className="preview-subject">
              <strong>{t('sendComposer.subject')}:</strong> {preview.subject}
            </p>
            <div
              className="preview-body"
              // Resolved server-side from our own template body; read-only preview.
              dangerouslySetInnerHTML={{ __html: preview.body_html }}
            />
          </div>
        )}

        <div className="est-actions">
          <button type="button" onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button type="button" onClick={runPreview} disabled={!hasTo}>
            {t('sendComposer.preview')}
          </button>
          <button
            type="button"
            className="est-primary"
            onClick={send}
            disabled={sending || !hasTo}
          >
            {t('sendComposer.send')}
          </button>
        </div>
      </div>
    </div>
  );
}
