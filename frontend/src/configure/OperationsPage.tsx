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
import type { OperationDefOut } from '../estimating/types';
import { useConfigureApi } from './api';

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
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
