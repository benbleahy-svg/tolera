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
import type { KalkCheckResult, OperationDefOut } from '../estimating/types';
import { useConfigureApi, type OperationDefUpdateBody } from './api';

/**
 * The operation-definition editor (spec op-def editor, "Edit operation
 * formula"): name, rates and the def-level Kalk formula behind the library
 * operation. Existing quote operations keep their snapshot (E4-d
 * config-freeze); the def-level Variables table (visibility eyes) needs a
 * def-evaluation endpoint and is logged as OPEN in DECISIONS.md.
 */
function OpDefDrawer({
  def,
  onSave,
  onClose,
  onKalkCheck,
}: {
  def: OperationDefOut;
  onSave: (body: OperationDefUpdateBody) => void;
  onClose: () => void;
  onKalkCheck: (formula: string) => Promise<KalkCheckResult>;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(def.name);
  const [runRate, setRunRate] = useState(def.run_rate ?? '');
  const [labourRate, setLabourRate] = useState(def.labour_rate ?? '');
  const [formula, setFormula] = useState(def.cost_formula ?? '');

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
              onSave={(body) => {
                setError(null);
                setEditingDefId(null);
                api
                  .updateOperationDef(def.id, body)
                  .then(() => reload(search))
                  .catch(fail);
              }}
              onClose={() => setEditingDefId(null)}
            />
          );
        })()}
    </main>
  );
}
