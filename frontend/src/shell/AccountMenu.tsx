/**
 * The sidebar bottom account area: user identity + active org, and a disclosure
 * menu holding the org-switcher (stub), appearance (theme), language, and sign-
 * out. Sign-out is injected (`onSignOut`) so the shell stays free of Clerk and
 * is unit-testable without an auth provider.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useSession, type SessionUser } from '../session/session';
import { BuildingIcon, ChevronIcon, SignOutIcon } from './icons';
import { LocaleToggle } from './LocaleToggle';
import { OrgSwitcher } from './OrgSwitcher';
import { ThemeToggle } from './ThemeToggle';

function displayName(user: SessionUser): string {
  const full = [user.first_name, user.last_name].filter(Boolean).join(' ').trim();
  return full || user.email;
}

export function AccountMenu({
  collapsed,
  onSignOut,
}: {
  collapsed: boolean;
  onSignOut?: () => void;
}) {
  const { t } = useTranslation();
  const { user, active_org } = useSession();
  const [open, setOpen] = useState(false);
  const name = displayName(user);

  return (
    <div className={open ? 'account open' : 'account'}>
      {open && (
        // A disclosure panel, not an ARIA menu: it mixes grouped controls and
        // static content, so role="menu"/menuitem (which implies roving focus +
        // arrow-key nav we don't implement) would mislead assistive tech.
        <div className="account-panel">
          <OrgSwitcher />
          <div className="menu-section">
            <div className="menu-label">{t('account.appearance')}</div>
            <ThemeToggle />
            <div className="menu-row static">
              <span>{t('account.language')}</span>
              <LocaleToggle />
            </div>
          </div>
          <button type="button" className="menu-row danger" onClick={onSignOut}>
            <SignOutIcon />
            <span>{t('account.sign_out')}</span>
          </button>
        </div>
      )}
      <button
        type="button"
        className="account-trigger"
        aria-label={t('account.menu')}
        aria-haspopup="true"
        aria-expanded={open}
        title={collapsed ? `${name} · ${active_org.name}` : undefined}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="avatar" aria-hidden="true">
          {(name[0] ?? '?').toUpperCase()}
        </span>
        {!collapsed && (
          <span className="account-id">
            <span className="account-name">{name}</span>
            <span className="account-org">
              <BuildingIcon /> {active_org.name}
            </span>
          </span>
        )}
        {!collapsed && (
          <span className="account-chevron">
            <ChevronIcon />
          </span>
        )}
      </button>
    </div>
  );
}
