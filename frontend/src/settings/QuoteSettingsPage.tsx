/**
 * Settings → Finalized Quote Settings (M5.8, spec #digital-quote-settings). The
 * one page that persists the org's `org_quote_settings` row: Quote Display
 * Settings (the toggles the portal + PDF read), Terms & Conditions (+ require
 * acceptance), Manufacturer's / Quote Notes, the Requotes toggle, Checkout
 * Settings (Allow Local Pickup / disable shipping methods / order-confirmation
 * emails), the Lead-Time business-vs-calendar preference, the Email-Notification
 * recipient matrix, and an informational Default Tax Rate. German-first copy.
 *
 * Save PUTs the whole draft (a partial-friendly endpoint — nullable content/rate
 * fields may be null); the backend re-enforces every gate the page renders.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  DISABLEABLE_SHIPPING_METHODS,
  NOTIFICATION_KEYS,
  SHOW_FLAG_KEYS,
  useQuoteSettingsApi,
  type NotificationKey,
  type QuoteSettings,
  type ShippingMethod,
} from './quoteSettings';

const TOTAL_DISPLAY_OPTIONS = ['price_range', 'maximum_price', 'none'] as const;
const PREPARER_OPTIONS = ['salesperson', 'estimator', 'both'] as const;
const NOTES_PLACEMENT_OPTIONS = ['above', 'below'] as const;

export function QuoteSettingsPage() {
  const { t } = useTranslation();
  const api = useQuoteSettingsApi();
  const [draft, setDraft] = useState<QuoteSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    api
      .get()
      .then(setDraft)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  const patch = (change: Partial<QuoteSettings>) => {
    setSaved(false);
    setDraft((prev) => (prev ? { ...prev, ...change } : prev));
  };

  const toggleDisabledMethod = (method: ShippingMethod, offered: boolean) => {
    if (!draft) return;
    const set = new Set(draft.disabled_shipping_methods);
    // The checkbox reads "offer this method" — checked ⇒ NOT disabled.
    if (offered) set.delete(method);
    else set.add(method);
    patch({ disabled_shipping_methods: [...set] });
  };

  const setRecipient = (key: NotificationKey, value: string) => {
    if (!draft) return;
    patch({
      notification_recipients: {
        ...draft.notification_recipients,
        [key]: value.trim() === '' ? null : value.trim(),
      },
    });
  };

  const save = () => {
    if (!draft) return;
    setSaving(true);
    setError(null);
    api
      .update(draft)
      .then((next) => {
        setDraft(next);
        setSaved(true);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setSaving(false));
  };

  if (error && !draft) {
    return <p role="alert">{error}</p>;
  }
  if (!draft) {
    return <p>{t('common.loading')}</p>;
  }

  return (
    <div className="quote-settings">
      <h1>{t('quoteSettings.heading')}</h1>

      <section aria-labelledby="qs-display">
        <h2 id="qs-display">{t('quoteSettings.display_heading')}</h2>
        <p>{t('quoteSettings.display_hint')}</p>
        {SHOW_FLAG_KEYS.map((key) => (
          <label key={key} className="qs-toggle">
            <input
              type="checkbox"
              checked={draft[key] as boolean}
              onChange={(e) => patch({ [key]: e.target.checked } as Partial<QuoteSettings>)}
            />
            {t(`quoteSettings.flag.${key}`)}
          </label>
        ))}
        <label className="qs-field">
          {t('quoteSettings.total_display')}
          <select
            value={draft.total_display}
            onChange={(e) =>
              patch({ total_display: e.target.value as QuoteSettings['total_display'] })
            }
          >
            {TOTAL_DISPLAY_OPTIONS.map((o) => (
              <option key={o} value={o}>
                {t(`quoteSettings.total_display_opt.${o}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="qs-field">
          {t('quoteSettings.preparer')}
          <select
            value={draft.preparer}
            onChange={(e) => patch({ preparer: e.target.value as QuoteSettings['preparer'] })}
          >
            {PREPARER_OPTIONS.map((o) => (
              <option key={o} value={o}>
                {t(`quoteSettings.preparer_opt.${o}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="qs-field">
          {t('quoteSettings.notes_placement')}
          <select
            value={draft.notes_placement}
            onChange={(e) =>
              patch({ notes_placement: e.target.value as QuoteSettings['notes_placement'] })
            }
          >
            {NOTES_PLACEMENT_OPTIONS.map((o) => (
              <option key={o} value={o}>
                {t(`quoteSettings.notes_placement_opt.${o}`)}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section aria-labelledby="qs-content">
        <h2 id="qs-content">{t('quoteSettings.content_heading')}</h2>
        <label className="qs-field">
          {t('quoteSettings.terms')}
          <textarea
            value={draft.terms ?? ''}
            onChange={(e) => patch({ terms: e.target.value === '' ? null : e.target.value })}
          />
        </label>
        <label className="qs-toggle">
          <input
            type="checkbox"
            checked={draft.require_terms_acceptance}
            onChange={(e) => patch({ require_terms_acceptance: e.target.checked })}
          />
          {t('quoteSettings.require_terms_acceptance')}
        </label>
        <label className="qs-field">
          {t('quoteSettings.manufacturers_notes')}
          <textarea
            value={draft.manufacturers_notes ?? ''}
            onChange={(e) =>
              patch({ manufacturers_notes: e.target.value === '' ? null : e.target.value })
            }
          />
        </label>
        <label className="qs-field">
          {t('quoteSettings.quote_notes')}
          <textarea
            value={draft.quote_notes ?? ''}
            onChange={(e) => patch({ quote_notes: e.target.value === '' ? null : e.target.value })}
          />
        </label>
      </section>

      <section aria-labelledby="qs-requotes">
        <h2 id="qs-requotes">{t('quoteSettings.requotes_heading')}</h2>
        <label className="qs-toggle">
          <input
            type="checkbox"
            checked={draft.requotes_enabled}
            onChange={(e) => patch({ requotes_enabled: e.target.checked })}
          />
          {t('quoteSettings.requotes_enabled')}
        </label>
      </section>

      <section aria-labelledby="qs-checkout">
        <h2 id="qs-checkout">{t('quoteSettings.checkout_heading')}</h2>
        <label className="qs-toggle">
          <input
            type="checkbox"
            checked={draft.allow_local_pickup}
            onChange={(e) => patch({ allow_local_pickup: e.target.checked })}
          />
          {t('quoteSettings.allow_local_pickup')}
        </label>
        <label className="qs-toggle">
          <input
            type="checkbox"
            checked={draft.send_order_confirmation_emails}
            onChange={(e) => patch({ send_order_confirmation_emails: e.target.checked })}
          />
          {t('quoteSettings.send_order_confirmation_emails')}
        </label>
        <fieldset>
          <legend>{t('quoteSettings.offered_methods')}</legend>
          {DISABLEABLE_SHIPPING_METHODS.map((method) => (
            <label key={method} className="qs-toggle">
              <input
                type="checkbox"
                checked={!draft.disabled_shipping_methods.includes(method)}
                onChange={(e) => toggleDisabledMethod(method, e.target.checked)}
              />
              {t(`quoteSettings.shipping_method.${method}`)}
            </label>
          ))}
        </fieldset>
      </section>

      <section aria-labelledby="qs-leadtime">
        <h2 id="qs-leadtime">{t('quoteSettings.leadtime_heading')}</h2>
        <label className="qs-toggle">
          <input
            type="checkbox"
            checked={draft.lead_time_business_days}
            onChange={(e) => patch({ lead_time_business_days: e.target.checked })}
          />
          {t('quoteSettings.lead_time_business_days')}
        </label>
      </section>

      <section aria-labelledby="qs-notify">
        <h2 id="qs-notify">{t('quoteSettings.notifications_heading')}</h2>
        {NOTIFICATION_KEYS.map((key) => (
          <label key={key} className="qs-field">
            {t(`quoteSettings.notification.${key}`)}
            <input
              type="email"
              value={draft.notification_recipients[key] ?? ''}
              onChange={(e) => setRecipient(key, e.target.value)}
            />
          </label>
        ))}
      </section>

      <section aria-labelledby="qs-accounting">
        <h2 id="qs-accounting">{t('quoteSettings.accounting_heading')}</h2>
        <label className="qs-field">
          {t('quoteSettings.default_tax_rate')}
          <input
            type="number"
            min={0}
            max={100}
            step="0.01"
            value={draft.default_tax_rate_pct ?? ''}
            onChange={(e) =>
              patch({ default_tax_rate_pct: e.target.value === '' ? null : e.target.value })
            }
          />
          <span className="qs-hint">{t('quoteSettings.default_tax_rate_hint')}</span>
        </label>
      </section>

      <div className="qs-actions">
        <button type="button" onClick={save} disabled={saving}>
          {t('common.save')}
        </button>
        {saved && <span role="status">{t('quoteSettings.saved')}</span>}
        {error && <span role="alert">{error}</span>}
      </div>
    </div>
  );
}
