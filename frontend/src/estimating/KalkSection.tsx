/**
 * The drawer's Kalk panel (M1.9, spec #kalk-vars / #kalk-contexts):
 *
 * * **Formula editor** — a monospace textarea over this quote's snapshot
 *   (never the library def; E4-d config-freeze), with the CHECK button
 *   (static validation, line-numbered errors) and save.
 * * **Variables panel** — the declared variables from the evaluation report
 *   (first break), rendered in their groups: plain inputs, drop-down selects,
 *   table-row selects; quantity-specific variables get one input per break.
 *   Saving PUTs the override map and recalculates.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { KalkEditor } from './KalkEditor';
import type {
  KalkCheckResult,
  KalkDeclaredVariable,
  KalkQtyReport,
  OverrideScalar,
  VariableOverrideValue,
} from './types';

interface Props {
  /** Formula owner (operation name) for the editor header. */
  name?: string;
  formula: string | null;
  variableOverrides: Record<string, VariableOverrideValue>;
  loadReport: () => Promise<KalkQtyReport[]>;
  onCheck: (formula: string) => Promise<KalkCheckResult>;
  onSaveFormula: (formula: string | null) => void;
  onSaveOverrides: (overrides: Record<string, VariableOverrideValue>) => void;
  disabled?: boolean;
}

/** Drafts hold raw input text so in-progress typing (e.g. a German decimal
 * comma) is never rewritten under the user; parsing happens at save. */
type DraftValue = string | Record<string, string>;

/** Parse an override input string per the variable's declared type. */
function parseOverride(variable: KalkDeclaredVariable, raw: string): OverrideScalar | null {
  const text = raw.trim();
  if (text === '') return null;
  if (variable.value_type === 'string') return text;
  const value = Number(text.replace(',', '.')); // German decimal commas
  return Number.isFinite(value) ? value : null;
}

/** The stored override map → editable draft strings. */
function toDrafts(overrides: Record<string, VariableOverrideValue>): Record<string, DraftValue> {
  return Object.fromEntries(
    Object.entries(overrides).map(([name, value]) => [
      name,
      typeof value === 'object' && value !== null
        ? Object.fromEntries(Object.entries(value).map(([qty, v]) => [qty, String(v)]))
        : String(value),
    ]),
  );
}

function VariableInput({
  variable,
  quantities,
  draft,
  onChange,
}: {
  variable: KalkDeclaredVariable;
  quantities: number[];
  draft: DraftValue | undefined;
  onChange: (next: DraftValue | undefined) => void;
}) {
  const { t } = useTranslation();

  // drop-downs and table rows override by picking an option
  if (variable.kind === 'drop_down' || variable.kind === 'table_var') {
    const options = (variable.options ?? []).map((option) =>
      typeof option === 'object' && option !== null && 'row_number' in option
        ? { value: String(option.row_number), label: option.display }
        : { value: String(option), label: String(option) },
    );
    const current = typeof draft === 'string' ? draft : '';
    return (
      <select
        aria-label={variable.name}
        value={current}
        onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)}
      >
        <option value="">
          {t('kalk.calculated_option', { value: String(variable.value ?? '—') })}
        </option>
        {options.map(({ value, label }) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
    );
  }

  if (variable.quantity_specific) {
    const perQty = typeof draft === 'object' && draft !== null ? draft : {};
    return (
      <span className="est-kalk-perqty">
        {quantities.map((qty) => (
          <label key={qty}>
            <span>{qty}×</span>
            <input
              aria-label={`${variable.name} @${qty}`}
              value={perQty[String(qty)] ?? ''}
              onChange={(e) => {
                const next = { ...perQty };
                if (e.target.value.trim() === '') delete next[String(qty)];
                else next[String(qty)] = e.target.value;
                onChange(Object.keys(next).length ? next : undefined);
              }}
            />
          </label>
        ))}
      </span>
    );
  }

  return (
    <input
      aria-label={variable.name}
      value={typeof draft === 'string' ? draft : ''}
      placeholder={t('estimating.override_placeholder')}
      onChange={(e) => onChange(e.target.value.trim() === '' ? undefined : e.target.value)}
    />
  );
}

/** Draft strings → the API override map, typed per the declared variables. */
function draftsToOverrides(
  drafts: Record<string, DraftValue>,
  variables: KalkDeclaredVariable[],
): Record<string, VariableOverrideValue> {
  const byName = new Map(variables.map((v) => [v.name, v]));
  const overrides: Record<string, VariableOverrideValue> = {};
  for (const [name, draft] of Object.entries(drafts)) {
    const variable = byName.get(name);
    if (!variable) continue;
    if (variable.kind === 'table_var') {
      // table variables override by row number
      const row = Number(typeof draft === 'string' ? draft : '');
      if (Number.isFinite(row)) overrides[name] = row;
    } else if (typeof draft === 'object' && draft !== null) {
      const perQty: Record<string, OverrideScalar> = {};
      for (const [qty, text] of Object.entries(draft)) {
        const parsed = parseOverride(variable, text);
        if (parsed !== null) perQty[qty] = parsed;
      }
      if (Object.keys(perQty).length) overrides[name] = perQty;
    } else {
      const parsed = parseOverride(variable, draft);
      if (parsed !== null) overrides[name] = parsed;
    }
  }
  return overrides;
}

export function KalkSection({
  name,
  formula,
  variableOverrides,
  loadReport,
  onCheck,
  onSaveFormula,
  onSaveOverrides,
  disabled,
}: Props) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(formula ?? '');
  const [report, setReport] = useState<KalkQtyReport[] | null>(null);
  const [showHidden, setShowHidden] = useState(false);
  const [overrideDrafts, setOverrideDrafts] = useState<Record<string, DraftValue>>(() =>
    toDrafts(variableOverrides),
  );

  useEffect(() => {
    if (!formula) return;
    let cancelled = false;
    void loadReport()
      .then((data) => {
        if (!cancelled) setReport(data);
      })
      .catch(() => {
        if (!cancelled) setReport(null); // failed load: keep the panel hidden, no stale data
      });
    return () => {
      cancelled = true;
    };
  }, [formula, loadReport]);

  const first = report?.[0] ?? null;
  const quantities = (report ?? []).map((r) => r.quantity);
  // runtime/setup_time override via the manual-minutes pair above, never here
  const allVariables = (first?.declared_variables ?? []).filter(
    (v) => v.name !== 'runtime' && v.name !== 'setup_time',
  );
  // default_visible=False hides a variable from the quote-side panel unless the
  // estimator opts in ("Show hidden variables", spec op-def Variables table);
  // an already-overridden hidden variable stays visible so the override is
  // never invisible state.
  const hiddenCount = allVariables.filter(
    (v) => v.default_visible === false && overrideDrafts[v.name] === undefined,
  ).length;
  const variables = allVariables.filter(
    (v) => showHidden || v.default_visible !== false || overrideDrafts[v.name] !== undefined,
  );
  const grouped = new Set((first?.variable_groups ?? []).flatMap((g) => g.members));
  const ungrouped = variables.filter((v) => !grouped.has(v.name));

  const setOverride = (name: string, value: DraftValue | undefined) => {
    setOverrideDrafts((prev) => {
      const next = { ...prev };
      if (value === undefined) delete next[name];
      else next[name] = value;
      return next;
    });
  };

  const renderVariable = (variable: KalkDeclaredVariable) => (
    <label className="est-override-row" key={variable.name}>
      <span title={variable.description}>{variable.name}</span>
      <span className="est-calc-value">
        {t('estimating.calculated')}: {variable.value === null ? '—' : String(variable.value)}
      </span>
      <VariableInput
        variable={variable}
        quantities={quantities}
        draft={overrideDrafts[variable.name]}
        onChange={(next) => setOverride(variable.name, next)}
      />
    </label>
  );

  return (
    <section className="est-kalk">
      <KalkEditor value={draft} onChange={setDraft} name={name} onCheck={onCheck} />
      <div className="est-actions">
        <button
          type="button"
          disabled={disabled}
          onClick={() => onSaveFormula(draft.trim() === '' ? null : draft)}
        >
          {t('kalk.save_formula')}
        </button>
      </div>

      {formula && first && (
        <>
          <h4>{t('kalk.variables')}</h4>
          {hiddenCount > 0 && (
            <label className="est-show-hidden">
              <input
                type="checkbox"
                checked={showHidden}
                onChange={(e) => setShowHidden(e.target.checked)}
              />
              {t('kalk.show_hidden_variables', { count: hiddenCount })}
            </label>
          )}
          {first.errors.length > 0 && (
            <p className="est-kalk-errors" role="alert">
              {first.errors
                .map((err) =>
                  err.line !== null
                    ? t('kalk.error_at_line', { line: err.line, message: err.message })
                    : err.message,
                )
                .join('\n')}
            </p>
          )}
          {(first.variable_groups ?? []).map((group) => (
            <details key={group.name} open={!group.default_collapsed}>
              <summary>{group.name}</summary>
              {group.members
                .map((name) => variables.find((v) => v.name === name))
                .filter((v): v is KalkDeclaredVariable => v !== undefined)
                .map(renderVariable)}
            </details>
          ))}
          {ungrouped.map(renderVariable)}
          {variables.length > 0 && (
            <div className="est-actions">
              <button
                type="button"
                disabled={disabled}
                onClick={() => onSaveOverrides(draftsToOverrides(overrideDrafts, allVariables))}
              >
                {t('kalk.save_overrides')}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
