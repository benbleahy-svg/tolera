/**
 * Dashboard suggested-actions strip (M3.10, spec #ai-rule-suggest).
 *
 * Renders the org's open Rule Auto-Suggestions as non-blocking chips. Each is a
 * *suggestion only*: "Regel erstellen" opens the M3.8 Create Rule dialog
 * **pre-seeded** with the detected pattern, but no rule exists until the human
 * clicks CREATE RULE inside that dialog (the AI never authors a rule). "Ablehnen"
 * dismisses a suggestion so it is never surfaced again.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useConfigureApi } from '../configure/api';
import {
  type SuggestedActionOut,
  suggestionSeed,
  useRuleSuggestApi,
} from '../review/api';
import { CreateRuleModal, type NewRule } from '../review/CreateRuleModal';

// The pre-seeded condition uses the `text` signal; the other singletons are
// offered so the human can re-pick. The full #rules-paths tree is the Configure
// → Rules surface's job (M3.6); the pre-seed only needs a valid starting path.
const DOCUMENT_PATHS = ['text', 'part', 'files'];

export function SuggestedActionsStrip(): React.ReactElement | null {
  const { t } = useTranslation();
  const api = useRuleSuggestApi();
  const configure = useConfigureApi();
  const [actions, setActions] = useState<SuggestedActionOut[]>([]);
  const [editing, setEditing] = useState<SuggestedActionOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setActions(await api.listSuggestedActions());
    } catch {
      setError(t('rule_suggest.load_error'));
    }
  }, [api, t]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const dismiss = async (id: string) => {
    try {
      await api.dismissSuggestedAction(id);
      setActions((prev) => prev.filter((a) => a.id !== id));
    } catch {
      setError(t('rule_suggest.load_error'));
    }
  };

  const create = async (rule: NewRule) => {
    // No rule until this call — the human clicked CREATE RULE in the dialog.
    await configure.importRules(JSON.stringify([rule]));
    if (editing) await dismiss(editing.id);
  };

  const rows = actions.filter((a) => a.kind === 'rule_suggestion' && a.status === 'open');
  if (rows.length === 0 && !error) return null;

  return (
    <section aria-label={t('rule_suggest.heading')} className="dashboard-suggested-actions">
      <h2>{t('rule_suggest.heading')}</h2>
      {error && <p role="alert">{error}</p>}
      <ul className="suggested-actions">
        {rows.map((a) => (
          <li key={a.id} className="suggested-action-chip" data-testid="rule-suggestion">
            <span className="suggested-action-sentence">{a.payload.sentence}</span>
            <div className="suggested-action-buttons">
              <button type="button" onClick={() => setEditing(a)}>
                {t('rule_suggest.create_rule')}
              </button>
              <button type="button" onClick={() => void dismiss(a.id)}>
                {t('rule_suggest.dismiss')}
              </button>
            </div>
          </li>
        ))}
      </ul>
      {editing && (
        <CreateRuleModal
          documentPaths={DOCUMENT_PATHS}
          suggestion={suggestionSeed(editing.payload)}
          onCreate={create}
          onClose={() => setEditing(null)}
        />
      )}
    </section>
  );
}
