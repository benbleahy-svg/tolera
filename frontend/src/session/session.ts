/**
 * Session model + context — the shape of `GET /api/me` and the hook the shell
 * reads it through. Capabilities (`effective_permissions`) are computed server-
 * side from the M0.3 authz matrix; the UI gates nav/actions on them and never
 * re-encodes the role→capability mapping (DECISIONS.md 2026-06-24).
 */

import { createContext, useContext } from 'react';

export interface SessionUser {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
}

export interface SessionOrg {
  id: string;
  name: string;
  slug: string;
  country: string;
  currency: string;
  locale: string;
}

export interface Membership {
  org_id: string;
  org_name: string;
  org_slug: string;
  country: string;
  currency: string;
  locale: string;
  roles: string[];
  status: string;
}

export interface Me {
  user: SessionUser;
  active_org: SessionOrg;
  memberships: Membership[];
  effective_permissions: string[];
  roles: string[];
}

export const SessionContext = createContext<Me | null>(null);

/** The current session; throws if used outside a provider. */
export function useSession(): Me {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error('useSession must be used within a SessionProvider');
  }
  return ctx;
}

/** Whether the active-org membership grants `permission` (a wire capability). */
export function useHasPermission(permission: string): boolean {
  return useSession().effective_permissions.includes(permission);
}
