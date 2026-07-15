/**
 * Configure → Rules (M3.6, spec #rules-schema): review rules import/export as
 * ONE JSON string — portable and diffable. This page lists the org's rules
 * and owns the paste-in/copy-out flow; authoring (the two-column Create Rule
 * modal) arrives with M3.8.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ApiError } from '../api/client';
import { type RuleOut, useConfigureApi } from './api';

export function RulesPage() {
  const { t } = useTranslation();
  const api = useConfigureApi();
  const [rules, setRules] = useState<RuleOut[]>([]);
  const [exported, setExported] = useState('');
  const [pasted, setPasted] = useState('');
  const [summary, setSummary] = useState<{ created: number; updated: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fail = useCallback((e: unknown) => {
    setError(e instanceof ApiError ? e.message : String(e));
  }, []);

  const reload = useCallback(() => {
    api.listRules().then(setRules).catch(fail);
    api
      .exportRules()
      .then((r) => setExported(r.rules_json))
      .catch(fail);
  }, [api, fail]);

  useEffect(reload, [reload]);

  const doImport = () => {
    setError(null);
    setSummary(null);
    api
      .importRules(pasted)
      .then((result) => {
        setSummary(result);
        setPasted('');
        reload();
      })
      .catch(fail);
  };

  return (
    <main className="est-page">
      <nav className="est-subnav">
        <Link to="/configure">{t('configure.custom_tables')}</Link>
        <Link to="/configure/pricing">{t('configure.pricing')}</Link>
        <Link to="/configure/operations">{t('configure.operations')}</Link>
        <span aria-current="page">{t('configure.rules')}</span>
      </nav>
      <header className="est-header">
        <h2>{t('configure.rules')}</h2>
      </header>
      <p className="est-hint">{t('configure.rules_hint')}</p>
      {error && (
        <p className="est-error" role="alert">
          {error}
        </p>
      )}
      {summary && (
        <p className="est-hint" role="status">
          {t('rules.import_result', { created: summary.created, updated: summary.updated })}
        </p>
      )}

      <section className="est-section">
        <table className="est-table">
          <thead>
            <tr>
              <th>{t('rules.name')}</th>
              <th>{t('rules.combine')}</th>
              <th>{t('rules.signals')}</th>
              <th>{t('rules.resolutions')}</th>
              <th>{t('rules.active')}</th>
            </tr>
          </thead>
          <tbody>
            {rules.length === 0 && (
              <tr>
                <td colSpan={5}>{t('rules.empty')}</td>
              </tr>
            )}
            {rules.map((rule) => (
              <tr key={rule.id}>
                <td title={rule.description}>{rule.name}</td>
                <td>{t(`rules.op_${rule.logical_operator.toLowerCase()}`)}</td>
                <td>{rule.signals.length}</td>
                <td>{rule.resolutions.length}</td>
                <td>{rule.is_active ? t('common.yes') : t('common.no')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="est-section">
        <label>
          {t('rules.export_label')}
          <textarea
            readOnly
            rows={6}
            value={exported}
            spellCheck={false}
            onFocus={(e) => e.currentTarget.select()}
          />
        </label>
      </section>

      <section className="est-section">
        <label>
          {t('rules.import_label')}
          <textarea
            rows={6}
            value={pasted}
            spellCheck={false}
            placeholder='[{"uuid":"…","name":"…"}]'
            onChange={(e) => setPasted(e.target.value)}
          />
        </label>
        <button type="button" disabled={pasted.trim() === ''} onClick={doImport}>
          {t('rules.import_button')}
        </button>
      </section>
    </main>
  );
}
