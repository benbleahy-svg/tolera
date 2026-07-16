/**
 * Review Items panel — the burn-down list (spec #rules, #rules-lifecycle;
 * DemoC "line-item review panel").
 *
 * Each card carries the rule name (the type label), the matched callout, an
 * assignee, a checkbox, and its rule's 1–N suggested actions as stacked
 * one-click buttons. The panel filters by Unresolved / assignee / type.
 *
 * The resolutions rendered are **the rule's own** (`resolution_options`), never
 * a fixed list: §3 says a rule offers the outcomes that apply to it, and the
 * server refuses any other — so the buttons and the guard agree by construction.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  resolutionLabel,
  useReviewApi,
  type PriorDecisionOut,
  type ResolutionOption,
  type ReviewItemOut,
} from './api';

interface Member {
  user_id: string;
  display_name: string;
}

interface Props {
  componentId: string;
  members?: Member[];
  /** Told when an item resolves, so the router/costing above can refetch. */
  onResolved?: (item: ReviewItemOut) => void;
}

const ANY = '__any__';

export function ReviewItemsPanel({ componentId, members = [], onResolved }: Props) {
  const { t } = useTranslation();
  const api = useReviewApi();
  const [items, setItems] = useState<ReviewItemOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [onlyUnresolved, setOnlyUnresolved] = useState(true);
  const [assignee, setAssignee] = useState<string>(ANY);
  const [type, setType] = useState<string>(ANY);

  const load = useCallback(async () => {
    try {
      setItems(await api.listForComponent(componentId));
      setError(null);
    } catch {
      setError(t('review.load_failed'));
    }
  }, [api, componentId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const ruleNames = useMemo(
    () => [...new Set(items.map((i) => i.rule_name))].sort((a, b) => a.localeCompare(b)),
    [items],
  );

  const visible = items.filter(
    (i) =>
      (!onlyUnresolved || i.status === 'open') &&
      (assignee === ANY || i.assignee_id === assignee) &&
      (type === ANY || i.rule_name === type),
  );
  const unresolved = items.filter((i) => i.status === 'open').length;

  const resolve = async (item: ReviewItemOut, option: ResolutionOption) => {
    setBusy(item.id);
    try {
      const updated = await api.resolve(item.id, option.type, option.custom_label);
      setItems((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
      onResolved?.(updated);
      setError(null);
    } catch {
      setError(t('review.resolve_failed'));
    } finally {
      setBusy(null);
    }
  };

  const reassign = async (item: ReviewItemOut, userId: string) => {
    try {
      const updated = await api.assign(item.id, userId === ANY ? null : userId);
      setItems((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
    } catch {
      setError(t('review.assign_failed'));
    }
  };

  return (
    <section className="review-panel" aria-label={t('review.panel_title')}>
      <header className="review-panel-header">
        <h3>{t('review.panel_title')}</h3>
        <span className="review-count" data-testid="review-unresolved-count">
          {t('review.unresolved_count', { count: unresolved })}
        </span>
      </header>

      {error ? <p role="alert">{error}</p> : null}

      <div className="review-filters">
        <label>
          <input
            type="checkbox"
            checked={onlyUnresolved}
            onChange={(e) => setOnlyUnresolved(e.target.checked)}
          />
          {t('review.filter_unresolved')}
        </label>
        <label>
          {t('review.filter_assignee')}
          <select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
            <option value={ANY}>{t('review.filter_anybody')}</option>
            {members.map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {m.display_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('review.filter_type')}
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value={ANY}>{t('review.filter_any_type')}</option>
            {ruleNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {visible.length === 0 ? (
        <p className="review-empty">{t('review.empty')}</p>
      ) : (
        <ul className="review-cards">
          {visible.map((item) => (
            <ReviewCard
              key={item.id}
              item={item}
              members={members}
              busy={busy === item.id}
              onResolve={(option) => resolve(item, option)}
              onReassign={(userId) => reassign(item, userId)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

interface CardProps {
  item: ReviewItemOut;
  members: Member[];
  busy: boolean;
  onResolve: (option: ResolutionOption) => void;
  onReassign: (userId: string) => void;
}

function ReviewCard({ item, members, busy, onResolve, onReassign }: CardProps) {
  const { t } = useTranslation();
  const api = useReviewApi();
  const [priors, setPriors] = useState<PriorDecisionOut[] | null>(null);
  const resolved = item.status === 'resolved';
  const callout = typeof item.detail.matched_text === 'string' ? item.detail.matched_text : null;

  /** §6.4: up to 5 past parts the rule flagged + the decision taken there —
   * fetched on demand, so a long panel does not N+1 on load. */
  const showPriors = async () => {
    if (priors !== null) {
      setPriors(null);
      return;
    }
    try {
      setPriors(await api.priorDecisions(item.id));
    } catch {
      setPriors([]);
    }
  };

  return (
    <li className="review-card" data-status={item.status} data-testid="review-card">
      <div className="review-card-head">
        <input type="checkbox" checked={resolved} readOnly aria-label={t('review.resolved')} />
        <span className="review-type">{item.rule_name}</span>
        <select
          className="review-assignee"
          aria-label={t('review.assignee')}
          value={item.assignee_id ?? ANY}
          onChange={(e) => onReassign(e.target.value)}
        >
          <option value={ANY}>{t('review.unassigned')}</option>
          {members.map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {m.display_name}
            </option>
          ))}
        </select>
      </div>

      {callout ? <p className="review-callout">{callout}</p> : null}

      {resolved ? (
        <p className="review-resolved-note">
          {t('review.resolved_as', {
            label: item.resolution_label ?? t(`review.resolution.${item.resolution_type}`),
          })}
        </p>
      ) : (
        <div className="review-actions">
          {item.resolution_options.map((option, idx) => (
            <button
              key={`${option.type}-${idx}`}
              type="button"
              className="review-action"
              data-resolution={option.type}
              disabled={busy}
              onClick={() => onResolve(option)}
            >
              {resolutionLabel(option, t)}
            </button>
          ))}
        </div>
      )}

      <button type="button" className="review-priors-toggle" onClick={showPriors}>
        {t('review.prior_decisions')}
      </button>
      {priors !== null ? (
        <ul className="review-priors">
          {priors.length === 0 ? (
            <li className="review-priors-empty">{t('review.no_prior_decisions')}</li>
          ) : (
            priors.map((p) => (
              <li key={p.id}>{p.resolution_label ?? t(`review.resolution.${p.resolution_type}`)}</li>
            ))
          )}
        </ul>
      ) : null}
    </li>
  );
}
