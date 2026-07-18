/**
 * Configure → Operations (M1.14, spec #operation-rates-banner): the
 * quick-start banner — "N Arbeitsgänge ohne Satz" with a single rate applied
 * to every unrated operation in one write — above the per-operation table
 * (name, mode, inline run-rate edit). The banner collapses once nothing is
 * unrated; configured rates are never overwritten by APPLY TO ALL.
 */

import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { KalkEditor } from '../estimating/KalkEditor';
import type {
  KalkCheckResult,
  KalkDeclaredVariable,
  OpDefKalkReport,
  OperationDefOut,
} from '../estimating/types';
import { useConfigureApi, type OperationDefUpdateBody } from './api';

/**
 * M4.14 — the def editor's Variables table (spec op-def editor: columns
 * VARIABLE | WERT | SICHTBARKEIT, variable search, "Show hidden variables"):
 * the saved formula evaluated def-level against the synthetic context. The
 * eye toggle PUTs the def's visibility map; attached quote operations keep
 * their attach-time snapshot (E4-d). The runtime/setup_time specials stay
 * out — they override via the manual-minutes pair (DECISIONS.md 2026-07-08).
 * WERT shows the formula default read-only (default-value editing is not in
 * this block); variable groups render flat here — the grouping chrome is a
 * quote-side concern.
 */
function DefVariablesTable({
  report,
  pending,
  onToggle,
}: {
  report: OpDefKalkReport;
  pending: boolean;
  onToggle: (next: Record<string, boolean>) => void;
}) {
  const { t } = useTranslation();
  const [showHidden, setShowHidden] = useState(false);
  const [search, setSearch] = useState('');

  const allVariables = report.declared_variables.filter(
    (v) => v.name !== 'runtime' && v.name !== 'setup_time',
  );
  const hiddenCount = allVariables.filter((v) => v.default_visible === false).length;
  const query = search.trim().toLowerCase();
  const variables = allVariables
    .filter((v) => showHidden || v.default_visible !== false)
    .filter((v) => query === '' || v.name.toLowerCase().includes(query));

  // the PUT base is the server's stored map from the report — a cached
  // defs-list row could be stale and would wipe earlier toggles
  const toggle = (variable: KalkDeclaredVariable) => {
    onToggle({ ...report.variable_visibility, [variable.name]: !variable.default_visible });
  };

  return (
    <section className="est-def-variables">
      <h4>{t('kalk.variables')}</h4>
      {report.errors.length > 0 && (
        <p className="est-kalk-errors" role="alert">
          {report.errors
            .map((err) =>
              err.line !== null
                ? t('kalk.error_at_line', { line: err.line, message: err.message })
                : err.message,
            )
            .join('\n')}
        </p>
      )}
      {allVariables.length > 0 && (
        <>
          <input
            value={search}
            placeholder={t('configure.search_variables')}
            aria-label={t('configure.search_variables')}
            onChange={(e) => setSearch(e.target.value)}
          />
          {hiddenCount > 0 && (
            <label className="est-show-hidden">
              <input
                type="checkbox"
                checked={showHidden}
                aria-label={t('kalk.show_hidden_variables', { count: hiddenCount })}
                onChange={(e) => setShowHidden(e.target.checked)}
              />
              {t('kalk.show_hidden_variables', { count: hiddenCount })}
            </label>
          )}
          <table className="est-table">
            <thead>
              <tr>
                <th>{t('configure.variables_variable')}</th>
                <th className="est-num">{t('configure.variables_value')}</th>
                <th>{t('configure.variables_visibility')}</th>
              </tr>
            </thead>
            <tbody>
              {variables.map((variable) => (
                <tr key={variable.name}>
                  <td title={variable.description}>{variable.name}</td>
                  <td className="est-num">
                    {variable.value === null
                      ? '—'
                      : typeof variable.value === 'number'
                        ? new Intl.NumberFormat('de-DE').format(variable.value)
                        : String(variable.value)}
                  </td>
                  <td>
                    <button
                      type="button"
                      className={
                        variable.default_visible === false ? 'est-eye est-eye-off' : 'est-eye'
                      }
                      disabled={pending}
                      aria-pressed={variable.default_visible !== false}
                      aria-label={t('configure.toggle_visibility', { name: variable.name })}
                      onClick={() => toggle(variable)}
                    >
                      👁
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

/**
 * The operation-definition editor (spec op-def editor, "Edit operation
 * formula"): name, rates, the def-level Kalk formula and its Variables
 * table (M4.14). Existing quote operations keep their snapshot (E4-d
 * config-freeze). The table reflects the last-saved formula — saving
 * closes the drawer; reopening re-evaluates.
 */
function OpDefDrawer({
  def,
  onSave,
  onClose,
  onKalkCheck,
  onLoadReport,
  onSetVisibility,
}: {
  def: OperationDefOut;
  onSave: (body: OperationDefUpdateBody) => void;
  onClose: () => void;
  onKalkCheck: (formula: string) => Promise<KalkCheckResult>;
  onLoadReport: (defId: string) => Promise<OpDefKalkReport>;
  onSetVisibility: (
    defId: string,
    visibility: Record<string, boolean>,
  ) => Promise<OpDefKalkReport>;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(def.name);
  const [runRate, setRunRate] = useState(def.run_rate ?? '');
  const [labourRate, setLabourRate] = useState(def.labour_rate ?? '');
  const [formula, setFormula] = useState(def.cost_formula ?? '');
  const [report, setReport] = useState<OpDefKalkReport | null>(null);
  const [togglePending, setTogglePending] = useState(false);
  const [variablesError, setVariablesError] = useState<string | null>(null);

  const hasSavedFormula = def.cost_formula != null;
  useEffect(() => {
    if (!hasSavedFormula) return;
    let cancelled = false;
    onLoadReport(def.id)
      .then((data) => {
        if (!cancelled) setReport(data);
      })
      .catch(() => {
        // failed load: no table, no stale data — but say so
        if (!cancelled) {
          setReport(null);
          setVariablesError(t('configure.variables_load_failed'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [hasSavedFormula, onLoadReport, def.id, t]);

  const blankToNull = (v: string): string | null => (v.trim() === '' ? null : v.trim());

  return (
    <aside className="est-drawer" aria-label={t('configure.op_def_drawer', { name: def.name })}>
      <header>
        <h3>{def.name}</h3>
        <button type="button" onClick={onClose} aria-label={t('common.close')}>
          ×
        </button>
      </header>
      <section>
        <label className="est-override-row">
          <span>{t('configure.op_name')}</span>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="est-override-row">
          <span>{t('estimating.run_rate')}</span>
          <input value={runRate} onChange={(e) => setRunRate(e.target.value)} />
        </label>
        {def.calculation_mode === 'machine_plus_operator' && (
          <label className="est-override-row">
            <span>{t('estimating.labour_rate')}</span>
            <input value={labourRate} onChange={(e) => setLabourRate(e.target.value)} />
          </label>
        )}
      </section>
      <KalkEditor
        value={formula}
        onChange={setFormula}
        name={name.trim() === '' ? undefined : name.trim()}
        onCheck={onKalkCheck}
      />
      {variablesError && (
        <p className="est-kalk-errors" role="alert">
          {variablesError}
        </p>
      )}
      {report && (
        <DefVariablesTable
          report={report}
          pending={togglePending}
          onToggle={(next) => {
            setTogglePending(true);
            setVariablesError(null);
            void onSetVisibility(def.id, next)
              .then(setReport)
              .catch(() => {
                // a failed toggle leaves the previous state untouched
                setVariablesError(t('configure.visibility_save_failed'));
              })
              .finally(() => setTogglePending(false));
          }}
        />
      )}
      <footer className="est-actions">
        <button type="button" onClick={onClose}>
          {t('common.cancel')}
        </button>
        <button
          type="button"
          disabled={name.trim() === ''}
          onClick={() => {
            const body: OperationDefUpdateBody = {
              name: name.trim(),
              run_rate: blankToNull(runRate.replace(',', '.')),
              cost_formula: blankToNull(formula),
            };
            if (def.calculation_mode === 'machine_plus_operator') {
              body.labour_rate = blankToNull(labourRate.replace(',', '.'));
            }
            onSave(body);
          }}
        >
          {t('estimating.save_changes')}
        </button>
      </footer>
    </aside>
  );
}

/** Mirrors the backend rule: rate-bearing defs only, NULL or 0 = missing. */
function defNeedsRate(def: OperationDefOut): boolean {
  return (
    def.category !== 'material' &&
    def.calculation_mode !== 'outside_process' &&
    def.cost_formula == null &&
    (def.run_rate == null || Number(def.run_rate) === 0)
  );
}

export function OperationsPage() {
  const { t } = useTranslation();
  const api = useConfigureApi();
  const [defs, setDefs] = useState<OperationDefOut[]>([]);
  const [unratedOps, setUnratedOps] = useState(0);
  const [unratedMaterials, setUnratedMaterials] = useState(0);
  const [quickRate, setQuickRate] = useState('');
  const [search, setSearch] = useState('');
  const [editingDefId, setEditingDefId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fail = useCallback((e: unknown) => {
    setError(e instanceof ApiError ? e.message : String(e));
  }, []);

  const reload = useCallback(
    (q: string) => {
      api.listOperationDefs(q).then(setDefs).catch(fail);
      api
        .getConfigCompleteness()
        .then((c) => {
          setUnratedOps(c.unrated_operation_defs);
          setUnratedMaterials(c.unrated_materials);
        })
        .catch(fail);
    },
    [api, fail],
  );

  useEffect(() => reload(''), [reload]);

  const saveRate = (defId: string, raw: string) => {
    const trimmed = raw.trim().replace(',', '.');
    if (trimmed === '') return;
    setError(null);
    api
      .updateOperationDef(defId, { run_rate: trimmed })
      .then(() => reload(search))
      .catch(fail);
  };

  return (
    <main className="configure-page">
      <nav className="est-subnav">
        <Link to="/configure">{t('configure.custom_tables')}</Link>
        <Link to="/configure/pricing">{t('configure.pricing')}</Link>
        <span aria-current="page">{t('configure.operations')}</span>
        <Link to="/configure/rules">{t('configure.rules')}</Link>
        <Link to="/configure/interrogations">{t('configure.interrogations')}</Link>
      </nav>
      <h1>{t('configure.operations')}</h1>
      {error && <p role="alert">{error}</p>}

      {(unratedOps > 0 || unratedMaterials > 0) && (
        <section className="est-warning-banner" role="status">
          <p>
            {t('configure.rates_banner', { count: unratedOps })}
            {unratedMaterials > 0 && (
              <> {t('configure.rates_banner_materials', { count: unratedMaterials })}</>
            )}
          </p>
          <label>
            {t('configure.quick_rate_label')}
            <input
              value={quickRate}
              size={8}
              aria-label={t('configure.quick_rate_label')}
              onChange={(e) => setQuickRate(e.target.value)}
            />
          </label>
          <button
            type="button"
            disabled={!quickRate.trim()}
            onClick={() => {
              setError(null);
              api
                .applyRateToAll(quickRate.trim().replace(',', '.'))
                .then(() => {
                  setQuickRate('');
                  reload(search);
                })
                .catch(fail);
            }}
          >
            {t('configure.apply_to_all')}
          </button>
        </section>
      )}

      <input
        value={search}
        placeholder={t('configure.search_operations')}
        aria-label={t('configure.search_operations')}
        onChange={(e) => {
          setSearch(e.target.value);
          reload(e.target.value);
        }}
      />
      <table className="est-table">
        <thead>
          <tr>
            <th>{t('configure.op_name')}</th>
            <th>{t('configure.op_mode')}</th>
            <th className="est-num">{t('configure.op_run_rate')}</th>
            <th aria-label={t('estimating.row_actions')} />
          </tr>
        </thead>
        <tbody>
          {defs.map((def) => (
            <tr key={def.id} className={defNeedsRate(def) ? 'est-missing-rate' : undefined}>
              <td>{def.name}</td>
              <td>{t(`configure.mode_${def.calculation_mode}`)}</td>
              <td className="est-num">
                <input
                  defaultValue={def.run_rate ?? ''}
                  size={8}
                  aria-label={t('configure.rate_input_label', { name: def.name })}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') saveRate(def.id, e.currentTarget.value);
                  }}
                  onBlur={(e) => {
                    if (e.target.value !== (def.run_rate ?? '')) saveRate(def.id, e.target.value);
                  }}
                />
              </td>
              <td className="est-row-actions">
                <button
                  type="button"
                  onClick={() => setEditingDefId(def.id)}
                  aria-label={t('configure.edit_op_def_label', { name: def.name })}
                >
                  ↗
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {editingDefId &&
        (() => {
          const def = defs.find((d) => d.id === editingDefId);
          if (!def) return null;
          return (
            <OpDefDrawer
              key={def.id}
              def={def}
              onKalkCheck={api.kalkCheck}
              onLoadReport={api.getOpDefKalkReport}
              onSetVisibility={api.setOpDefVariableVisibility}
              onSave={(body) => {
                setError(null);
                // close only on success — a failed save keeps the drawer
                // (and the estimator's edits) alive with the error shown
                api
                  .updateOperationDef(def.id, body)
                  .then(() => {
                    setEditingDefId(null);
                    reload(search);
                  })
                  .catch(fail);
              }}
              onClose={() => setEditingDefId(null)}
            />
          );
        })()}
    </main>
  );
}
