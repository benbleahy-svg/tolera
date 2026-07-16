/**
 * Create Rule — the two-column modal (spec #rules "Create Rule dialog";
 * DemoC/06–09). Left = the rule editor, right = a live Preview of the card the
 * rule will produce, so the author sees the thing they are creating.
 *
 * Reached two ways (spec):
 *  (a) from scratch via the Signals picker;
 *  (b) from a callout popover's "Create rule" link, which pre-seeds a
 *      **"Selected item" signal** from the clicked entity — the
 *      "build a Review rule from this finding" path (§8).
 *
 * The signal picker here is deliberately the flat `document_path` catalogue
 * rather than the spec's cascading multi-column tree: the tree is presentation
 * over the same closed set (M3.6 `#rules-paths`), and the AST it must emit is
 * identical. Called out so the next block can restyle without re-deriving the
 * contract.
 *
 * **No rule is created without an explicit CREATE RULE click** — the footer
 * commit is the only writer, which is also what keeps M3.10's AI suggestion
 * human-gated (it may only pre-seed this dialog).
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ResolutionType } from './api';

/** The pre-seed from a callout popover — the clicked finding (§8). */
export interface SelectedItem {
  /** Human-readable pill, e.g. "⌖ ⌀0,05 A B". */
  label: string;
  document_path: string;
  field_name: string;
  /** mm/deg already — the panel never hands the editor an imperial value (§7). */
  value: number;
  units: 'mm' | 'deg';
}

export interface NewRule {
  uuid: string;
  name: string;
  description: string;
  logical_operator: 'AND' | 'OR';
  signals: unknown[];
  resolutions: { type: ResolutionType; parameters: unknown[]; custom_label: string | null }[];
  default_assignee_id: string | null;
}

interface Member {
  user_id: string;
  display_name: string;
}

interface Props {
  /** The closed `document_path` catalogue (spec #rules-paths). */
  documentPaths: string[];
  members?: Member[];
  /** Set when opened from a callout popover; null when opened from scratch. */
  selectedItem?: SelectedItem | null;
  onCreate: (rule: NewRule) => Promise<void> | void;
  onClose: () => void;
}

type Comparison = 'lessThanOrEqual' | 'greaterThanOrEqual' | 'equals';

const RESOLUTION_TYPES: ResolutionType[] = [
  'ADD_OPERATION',
  'ASSIGN_ESTIMATOR',
  'SET_PROCESS',
  'NO_QUOTE',
  'RESOLVE',
];

export function CreateRuleModal({
  documentPaths,
  members = [],
  selectedItem = null,
  onCreate,
  onClose,
}: Props) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [documentPath, setDocumentPath] = useState(
    selectedItem?.document_path ?? documentPaths[0] ?? 'text',
  );
  const [fieldName, setFieldName] = useState(selectedItem?.field_name ?? 'raw_text');
  const [comparison, setComparison] = useState<Comparison>('lessThanOrEqual');
  const [value, setValue] = useState(selectedItem ? String(selectedItem.value) : '');
  const [units, setUnits] = useState<'mm' | 'deg'>(selectedItem?.units ?? 'mm');
  const [seeded, setSeeded] = useState(selectedItem);
  const [resolutions, setResolutions] = useState<
    { type: ResolutionType; custom_label: string | null }[]
  >([]);
  const [assigneeId, setAssigneeId] = useState<string>('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Numeric while a threshold is being compared; keyword otherwise. */
  const numeric = value.trim() !== '' && !Number.isNaN(Number(value.replace(',', '.')));

  const valid = name.trim().length > 0 && resolutions.length > 0 && value.trim().length > 0;

  const rule: NewRule = useMemo(() => {
    const parsed = Number(value.replace(',', '.'));
    const query = numeric
      ? {
          field_name: [fieldName],
          operator: comparison,
          value: parsed,
          value_type: units === 'deg' ? 'angle' : 'distance',
          filter_type: 'numeric',
          units,
        }
      : {
          field_name: [fieldName],
          operator: 'includesCaseInsensitive',
          value: [value],
          value_type: 'string',
          filter_type: 'string',
          units: null,
        };
    return {
      uuid: crypto.randomUUID(),
      name: name.trim(),
      description: description.trim(),
      logical_operator: 'OR',
      signals: [
        {
          logical_operator: 'AND',
          groups: [
            { document_path: documentPath, logical_operator: 'AND', queries: [query], count_query: null },
          ],
        },
      ],
      resolutions: resolutions.map((r) => ({
        type: r.type,
        parameters: [],
        custom_label: r.custom_label,
      })),
      default_assignee_id: assigneeId || null,
    };
  }, [
    assigneeId,
    comparison,
    description,
    documentPath,
    fieldName,
    name,
    numeric,
    resolutions,
    units,
    value,
  ]);

  const submit = async () => {
    if (!valid || saving) return;
    setSaving(true);
    try {
      await onCreate(rule);
      onClose();
    } catch {
      setError(t('review.create_rule_failed'));
      setSaving(false);
    }
  };

  return (
    <div className="est-modal-backdrop">
      <div className="est-modal review-rule-modal" role="dialog" aria-modal="true" aria-label={t('review.create_rule')}>
        <div className="review-rule-columns">
          {/* left: editor */}
          <div className="review-rule-editor">
            <h3>{t('review.create_rule')}</h3>

            <label>
              {t('review.rule_name')} *
              <input value={name} onChange={(e) => setName(e.target.value)} required />
            </label>
            <label>
              {t('review.rule_description')}
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} />
            </label>

            <fieldset className="review-rule-signals">
              <legend>{t('review.signals')}</legend>
              <p className="review-hint">{t('review.signals_hint')}</p>

              {seeded ? (
                <div className="review-selected-chip">
                  <span>{seeded.label}</span>
                  <button type="button" onClick={() => setSeeded(null)}>
                    {t('review.clear')}
                  </button>
                </div>
              ) : null}

              <label>
                {t('review.signal_path')}
                <select value={documentPath} onChange={(e) => setDocumentPath(e.target.value)}>
                  {documentPaths.map((path) => (
                    <option key={path} value={path}>
                      {path}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t('review.signal_field')}
                <input value={fieldName} onChange={(e) => setFieldName(e.target.value)} />
              </label>

              <div className="review-filter-row">
                <select
                  aria-label={t('review.comparison')}
                  value={comparison}
                  onChange={(e) => setComparison(e.target.value as Comparison)}
                >
                  <option value="lessThanOrEqual">≤</option>
                  <option value="greaterThanOrEqual">≥</option>
                  <option value="equals">=</option>
                </select>
                <input
                  aria-label={t('review.value')}
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                />
                {numeric ? (
                  <select
                    aria-label={t('review.units')}
                    value={units}
                    onChange={(e) => setUnits(e.target.value as 'mm' | 'deg')}
                  >
                    {/* Metric-native: the imperial path is dropped (CLAUDE.md §5). */}
                    <option value="mm">mm</option>
                    <option value="deg">deg</option>
                  </select>
                ) : null}
              </div>
            </fieldset>

            <fieldset className="review-rule-resolutions">
              <legend>{t('review.resolution_options')}</legend>
              <p className="review-hint">{t('review.resolutions_hint')}</p>
              <ul>
                {resolutions.map((r, idx) => (
                  <li key={`${r.type}-${idx}`}>
                    <span>{r.custom_label || t(`review.resolution.${r.type}`)}</span>
                    <button
                      type="button"
                      onClick={() => setResolutions((prev) => prev.filter((_, i) => i !== idx))}
                    >
                      {t('review.remove')}
                    </button>
                  </li>
                ))}
              </ul>
              <select
                aria-label={t('review.add_resolution')}
                value=""
                onChange={(e) => {
                  const type = e.target.value as ResolutionType;
                  if (!type) return;
                  setResolutions((prev) => [...prev, { type, custom_label: null }]);
                }}
              >
                <option value="">{t('review.add_resolution')}</option>
                {RESOLUTION_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {t(`review.resolution.${type}`)}
                  </option>
                ))}
              </select>
            </fieldset>

            {/* Spec: the Assignee field appears once a resolution is added. */}
            {resolutions.length > 0 ? (
              <>
                <label>
                  {t('review.assignee')}
                  <select value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)}>
                    <option value="">{t('review.unassigned')}</option>
                    {members.map((m) => (
                      <option key={m.user_id} value={m.user_id}>
                        {m.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                {/* Outside the <label>: nested inside, the hint becomes part of
                    the select's accessible name ("Zuständig Die zuständige
                    Person wird benachrichtigt…") — unusable for a screen reader
                    and for a name-based query. */}
                <p className="review-hint">{t('review.assignee_hint')}</p>
              </>
            ) : null}

            {error ? <p role="alert">{error}</p> : null}
          </div>

          {/* right: live preview of the resulting card */}
          <div className="review-rule-preview" aria-label={t('review.preview')}>
            <h4>{t('review.preview')}</h4>
            <div className="review-card" data-status="open">
              <div className="review-card-head">
                <input type="checkbox" checked={false} readOnly aria-hidden="true" tabIndex={-1} />
                <span className="review-type">{name.trim() || t('review.rule_name_placeholder')}</span>
              </div>
              {seeded ? <p className="review-callout">{seeded.label}</p> : null}
              <div className="review-actions">
                {resolutions.length === 0 ? (
                  <p className="review-hint">{t('review.preview_no_resolutions')}</p>
                ) : (
                  resolutions.map((r, idx) => (
                    <button key={`${r.type}-${idx}`} type="button" className="review-action" disabled>
                      {r.custom_label || t(`review.resolution.${r.type}`)}
                    </button>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>

        <footer className="est-modal-footer">
          <button type="button" onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button type="button" className="primary" disabled={!valid || saving} onClick={submit}>
            {t('review.create_rule_commit')}
          </button>
        </footer>
      </div>
    </div>
  );
}
