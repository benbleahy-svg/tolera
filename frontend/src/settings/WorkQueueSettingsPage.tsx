/**
 * Settings → Dashboard queue (M6.1, spec #newscope §2: "weights org-configurable
 * in Settings, sensible defaults shipped").
 *
 * Four numbers and a source toggle. Every field maps 1:1 to a column of
 * `org_dashboard_settings`; the backend re-validates (no negatives) and is the
 * authority — this page only has to make the trade-off legible, which is why the
 * copy names the factor rather than the column.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { type QueueWeights, useWorkQueueApi } from '../dashboard/workQueueApi';

const WEIGHT_FIELDS = [
  'weight_due',
  'weight_value',
  'weight_unresolved',
  'weight_flags',
] as const;

export function WorkQueueSettingsPage(): React.ReactElement {
  const { t } = useTranslation();
  const api = useWorkQueueApi();
  const [draft, setDraft] = useState<QueueWeights | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(() => {
    api
      .getSettings()
      .then(setDraft)
      // Always a translated message — never a raw backend/network string.
      .catch(() => setError(t('workQueueSettings.load_error')));
  }, [api, t]);

  useEffect(load, [load]);

  const save = async () => {
    if (!draft) return;
    setSaved(false);
    // `min={0}` on the inputs is not enforcement: this is a type="button"
    // handler, so nothing runs the browser's constraint validation and a blank
    // or negative field would reach the API as a 422 with no field-level
    // message. Check locally first (the backend still re-validates).
    const invalid = WEIGHT_FIELDS.some((field) => {
      const value = Number(draft[field]);
      return draft[field] === '' || !Number.isFinite(value) || value < 0;
    });
    if (invalid) {
      setError(t('workQueueSettings.invalid_weight'));
      return;
    }
    // A prior failure must not stay on screen through a successful retry.
    setError(null);
    try {
      setDraft(await api.saveSettings(draft));
      setSaved(true);
    } catch {
      setError(t('workQueueSettings.save_error'));
    }
  };

  if (!draft) {
    return <p role="alert">{error ?? ''}</p>;
  }

  return (
    <div className="settings-page">
      <h1>{t('workQueueSettings.title')}</h1>
      <p>{t('workQueueSettings.intro')}</p>
      {error && <p role="alert">{error}</p>}
      {WEIGHT_FIELDS.map((field) => (
        <label key={field}>
          {t(`workQueueSettings.${field}`)}
          <input
            type="number"
            min={0}
            step="0.05"
            value={draft[field]}
            onChange={(e) => setDraft({ ...draft, [field]: e.target.value })}
          />
        </label>
      ))}
      <label>
        <input
          type="checkbox"
          checked={draft.vendor_rfq_queue_enabled}
          onChange={(e) => setDraft({ ...draft, vendor_rfq_queue_enabled: e.target.checked })}
        />
        {t('workQueueSettings.vendor_rfq_queue_enabled')}
      </label>
      <button type="button" onClick={() => void save()}>
        {t('workQueueSettings.save')}
      </button>
      {saved && <p role="status">{t('workQueueSettings.saved')}</p>}
    </div>
  );
}
