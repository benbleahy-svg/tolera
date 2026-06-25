/**
 * Org-switcher — M0.4 stub (DECISIONS.md 2026-06-24 "Org-switcher location").
 * Lists every membership and marks the active org (resolved from the JWT claim).
 * Switching to another org is deferred to M5.12 (membership ↔ session-token
 * sync), so inactive rows are disabled with a "switching soon" hint.
 */

import { useTranslation } from 'react-i18next';

import { useSession } from '../session/session';
import { CheckIcon } from './icons';

export function OrgSwitcher() {
  const { t } = useTranslation();
  const { active_org, memberships } = useSession();

  return (
    <div className="org-switcher" role="group" aria-label={t('org.switcher_title')}>
      <div className="menu-label">{t('org.switcher_title')}</div>
      <ul className="org-list">
        {memberships.map((m) => {
          const isActive = m.org_id === active_org.id;
          return (
            <li key={m.org_id}>
              <button
                type="button"
                className={isActive ? 'org-row active' : 'org-row'}
                aria-current={isActive ? 'true' : undefined}
                disabled={!isActive}
                title={isActive ? t('org.active') : t('org.switch_unavailable')}
              >
                <span className="org-row-name">{m.org_name}</span>
                {isActive ? (
                  <CheckIcon />
                ) : (
                  <span className="org-row-hint">{t('org.switch_unavailable')}</span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
