/**
 * Primary navigation config — the seven destinations from spec #shell, rendered
 * in the sidebar (spec #ui-system; DECISIONS.md 2026-06-24 "Primary navigation
 * pattern"). Each item may declare the capability required to see it; visibility
 * is computed from the caller's `effective_permissions` (the M0.3 matrix), so
 * nav is role-aware without the frontend re-encoding any role logic.
 *
 * The destination pages themselves are out of M0.4 scope (Dashboard → M6,
 * Configure → M5, …); each routes to a localized placeholder for now.
 */

import type { ComponentType } from 'react';

import {
  AnalyticsIcon,
  ConfigureIcon,
  ContactsIcon,
  DashboardIcon,
  OrdersIcon,
  PartsIcon,
  QuotesIcon,
} from './icons';

export interface NavItem {
  to: string;
  labelKey: string;
  Icon: ComponentType;
  /** Capability required to see the item; undefined = always visible. */
  permission?: string;
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', labelKey: 'nav.dashboard', Icon: DashboardIcon },
  { to: '/parts', labelKey: 'nav.parts', Icon: PartsIcon, permission: 'view_all' },
  { to: '/quotes', labelKey: 'nav.quotes', Icon: QuotesIcon, permission: 'view_all' },
  { to: '/orders', labelKey: 'nav.orders', Icon: OrdersIcon, permission: 'view_all' },
  { to: '/contacts', labelKey: 'nav.contacts', Icon: ContactsIcon, permission: 'view_all' },
  { to: '/configure', labelKey: 'nav.configure', Icon: ConfigureIcon, permission: 'config_edit' },
  { to: '/analytics', labelKey: 'nav.analytics', Icon: AnalyticsIcon, permission: 'view_all' },
];

/** The nav items the given capabilities allow seeing. */
export function visibleNavItems(permissions: string[]): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.permission || permissions.includes(item.permission));
}
