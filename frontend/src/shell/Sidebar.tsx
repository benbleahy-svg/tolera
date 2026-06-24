/**
 * The primary navigation surface — a collapsible dark sidebar (spec #ui-system;
 * DECISIONS.md 2026-06-24). Top row: collapse/expand toggle + global search.
 * Nav: the destinations the caller's capabilities allow. Bottom: the account
 * area (identity, org-switcher, theme, language, sign-out). Collapse state
 * persists to localStorage and toggles with the `[` key.
 */

import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useSession } from '../session/session';
import { AccountMenu } from './AccountMenu';
import { BrandMark } from './BrandMark';
import { MenuIcon, PanelLeftIcon, SearchIcon } from './icons';
import { visibleNavItems } from './nav';

const COLLAPSE_KEY = 'bf-sidebar-collapsed';

function initialCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === 'true';
  } catch {
    return false;
  }
}

export function Sidebar({ onSignOut }: { onSignOut?: () => void }) {
  const { t } = useTranslation();
  const { effective_permissions } = useSession();
  const [collapsed, setCollapsed] = useState<boolean>(initialCollapsed);
  const items = visibleNavItems(effective_permissions);

  function toggle() {
    setCollapsed((current) => {
      const next = !current;
      try {
        localStorage.setItem(COLLAPSE_KEY, String(next));
      } catch {
        /* storage unavailable — collapse still applies for the session */
      }
      return next;
    });
  }

  // `[` toggles collapse (spec), but never while typing in a field.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== '[') return;
      const el = document.activeElement;
      if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) return;
      toggle();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <nav
      className={collapsed ? 'sidebar collapsed' : 'sidebar'}
      aria-label={t('shell.primary_nav')}
    >
      <NavLink to="/" className="brand-link" end>
        <BrandMark collapsed={collapsed} />
      </NavLink>

      <div className="sidebar-top">
        <button
          type="button"
          className="icon-btn"
          onClick={toggle}
          aria-label={collapsed ? t('shell.expand') : t('shell.collapse')}
          title={collapsed ? t('shell.expand') : t('shell.collapse')}
        >
          {collapsed ? <MenuIcon /> : <PanelLeftIcon />}
        </button>
        {!collapsed && (
          <div className="search">
            <SearchIcon />
            {/* Disabled until the ⌘K command palette lands (later block) — an
                enabled-but-inert field would mislead. */}
            <input
              type="search"
              placeholder={t('shell.search_placeholder')}
              aria-label={t('shell.search_placeholder')}
              disabled
            />
          </div>
        )}
      </div>

      <ul className="nav-list">
        {items.map(({ to, labelKey, Icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={to === '/'}
              className={({ isActive }) => (isActive ? 'nav-item active' : 'nav-item')}
              title={collapsed ? t(labelKey) : undefined}
            >
              <span className="nav-icon">
                <Icon />
              </span>
              {!collapsed && <span className="nav-label">{t(labelKey)}</span>}
            </NavLink>
          </li>
        ))}
      </ul>

      <AccountMenu collapsed={collapsed} onSignOut={onSignOut} />
    </nav>
  );
}
