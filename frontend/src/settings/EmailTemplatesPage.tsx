/**
 * Settings → Email Templates (M5.5, spec #email-templates, DemoH/08). Three
 * sections in order — Quote-send / Order-shipment / Order-refund — each a table
 * (Template name, Last edited by, Last edited, + a DEFAULT badge on the default
 * row) with a "CREATE NEW … TEMPLATE" button. Per row: Edit + Delete (Delete is
 * disabled for the default row; the backend also 409s `default_template_protected`
 * as a belt-and-braces guard we surface). The editor modal carries the merge-field
 * insert buttons that append a token to the Body. German-first copy.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { useEmailTemplatesApi } from './api';
import { MERGE_FIELDS } from './mergeFields';
import type {
  EmailTemplate,
  EmailTemplateCreateBody,
  EmailTemplateType,
  EmailTemplateUpdateBody,
} from './types';

const SECTIONS: EmailTemplateType[] = ['quote_send', 'order_shipment', 'order_refund'];

interface EditorState {
  type: EmailTemplateType;
  /** null → creating a new template of `type`; otherwise editing. */
  template: EmailTemplate | null;
}

export function EmailTemplatesPage() {
  const { t, i18n } = useTranslation();
  const api = useEmailTemplatesApi();
  const [templates, setTemplates] = useState<EmailTemplate[] | null>(null);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .list()
      .then(setTemplates)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  const formatDate = (value: string) => new Date(value).toLocaleDateString(i18n.language);

  const removeTemplate = (template: EmailTemplate) => {
    setError(null);
    api
      .remove(template.id)
      .then(load)
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.code === 'default_template_protected') {
          setError(t('emailTemplates.default_protected'));
        } else {
          setError(e instanceof Error ? e.message : String(e));
        }
      });
  };

  return (
    <div className="page email-templates">
      <header className="page-header">
        <h1>{t('emailTemplates.title')}</h1>
        <p className="page-subtitle">{t('emailTemplates.subtitle')}</p>
      </header>

      {error && (
        <div className="banner error" role="alert">
          {error}
        </div>
      )}

      {templates === null ? (
        <p>{t('common.loading')}</p>
      ) : (
        SECTIONS.map((type) => {
          const rows = templates.filter((tpl) => tpl.template_type === type);
          return (
            <section className="panel" key={type} aria-label={t(`emailTemplates.section.${type}`)}>
              <h2>{t(`emailTemplates.section.${type}`)}</h2>
              <table className="template-table">
                <thead>
                  <tr>
                    <th>{t('emailTemplates.col.name')}</th>
                    <th>{t('emailTemplates.col.last_edited_by')}</th>
                    <th>{t('emailTemplates.col.last_edited')}</th>
                    <th aria-label={t('emailTemplates.col.actions')} />
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="empty">
                        {t('emailTemplates.none')}
                      </td>
                    </tr>
                  ) : (
                    rows.map((tpl) => (
                      <tr key={tpl.id}>
                        <td>
                          {tpl.name}
                          {tpl.is_default && (
                            <span className="badge default">{t('emailTemplates.default_badge')}</span>
                          )}
                        </td>
                        <td>{tpl.last_edited_by ?? '—'}</td>
                        <td>{formatDate(tpl.updated_at)}</td>
                        <td className="template-actions">
                          <button
                            type="button"
                            onClick={() => setEditor({ type, template: tpl })}
                          >
                            {t('emailTemplates.edit')}
                          </button>
                          <button
                            type="button"
                            className="danger"
                            disabled={tpl.is_default}
                            title={tpl.is_default ? t('emailTemplates.default_protected') : undefined}
                            onClick={() => removeTemplate(tpl)}
                          >
                            {t('emailTemplates.delete')}
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
              <button
                type="button"
                className="create-template"
                onClick={() => setEditor({ type, template: null })}
              >
                {t(`emailTemplates.create.${type}`)}
              </button>
            </section>
          );
        })
      )}

      {editor && (
        <TemplateEditor
          type={editor.type}
          template={editor.template}
          onClose={() => setEditor(null)}
          onSaved={() => {
            setEditor(null);
            load();
          }}
          onError={setError}
        />
      )}
    </div>
  );
}

interface EditorProps {
  type: EmailTemplateType;
  template: EmailTemplate | null;
  onClose: () => void;
  onSaved: () => void;
  onError: (message: string) => void;
}

function TemplateEditor({ type, template, onClose, onSaved, onError }: EditorProps) {
  const { t } = useTranslation();
  const api = useEmailTemplatesApi();
  const [name, setName] = useState(template?.name ?? '');
  const [subject, setSubject] = useState(template?.subject ?? '');
  const [body, setBody] = useState(template?.body ?? '');
  const [isDefault, setIsDefault] = useState(template?.is_default ?? false);
  const [saving, setSaving] = useState(false);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  const insertToken = (token: string) => {
    const el = bodyRef.current;
    if (!el) {
      setBody((prev) => prev + token);
      return;
    }
    const start = el.selectionStart;
    const end = el.selectionEnd;
    setBody((prev) => prev.slice(0, start) + token + prev.slice(end));
    // Restore focus + caret just after the inserted token (next tick).
    requestAnimationFrame(() => {
      el.focus();
      const caret = start + token.length;
      el.setSelectionRange(caret, caret);
    });
  };

  const save = () => {
    setSaving(true);
    const done = () => {
      setSaving(false);
      onSaved();
    };
    const fail = (e: unknown) => {
      setSaving(false);
      onError(e instanceof Error ? e.message : String(e));
    };
    if (template) {
      const body_: EmailTemplateUpdateBody = { name, subject, body, is_default: isDefault };
      api.update(template.id, body_).then(done).catch(fail);
    } else {
      const body_: EmailTemplateCreateBody = {
        template_type: type,
        name,
        subject,
        body,
        is_default: isDefault,
      };
      api.create(body_).then(done).catch(fail);
    }
  };

  return (
    <div className="est-modal-backdrop" role="dialog" aria-label={t('emailTemplates.editor_title')}>
      <div className="est-modal template-editor">
        <h3>{template ? t('emailTemplates.edit') : t(`emailTemplates.create.${type}`)}</h3>
        <label className="form-field">
          <span>{t('emailTemplates.field_name')}</span>
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label className="form-field">
          <span>{t('emailTemplates.field_subject')}</span>
          <input value={subject} onChange={(e) => setSubject(e.target.value)} required />
        </label>
        <div className="merge-fields" aria-label={t('emailTemplates.merge_fields')}>
          <span className="merge-fields-label">{t('emailTemplates.merge_fields')}</span>
          {MERGE_FIELDS.map((field) => (
            <button
              type="button"
              key={field.token}
              className="merge-field-chip"
              onClick={() => insertToken(field.token)}
            >
              {t(field.labelKey)}
            </button>
          ))}
        </div>
        <label className="form-field">
          <span>{t('emailTemplates.field_body')}</span>
          <textarea
            ref={bodyRef}
            value={body}
            rows={10}
            onChange={(e) => setBody(e.target.value)}
            required
          />
        </label>
        <label className="form-check">
          <input
            type="checkbox"
            checked={isDefault}
            onChange={(e) => setIsDefault(e.target.checked)}
          />
          <span>{t('emailTemplates.set_default')}</span>
        </label>
        <div className="est-actions">
          <button type="button" onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button type="button" onClick={save} disabled={saving}>
            {t('common.save')}
          </button>
        </div>
      </div>
    </div>
  );
}
