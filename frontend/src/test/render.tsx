/**
 * Test helper: render shell components with the providers they need (router +
 * i18n + a fixed session). Deliberately Clerk-free — the shell reads the session
 * from context, so unit tests supply it directly without an auth provider.
 */

import type { ReactElement } from 'react';
import { render, type RenderResult } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';

import i18n, { localeToLanguage } from '../i18n';
import { SessionContext, type Me, type Membership, type SessionOrg } from '../session/session';

export function org(slug: string, name: string, extra: Partial<SessionOrg> = {}): SessionOrg {
  return {
    id: `org-${slug}`,
    name,
    slug,
    country: 'DE',
    currency: 'EUR',
    locale: 'de-DE',
    ...extra,
  };
}

export function membership(o: SessionOrg, roles: string[]): Membership {
  return {
    org_id: o.id,
    org_name: o.name,
    org_slug: o.slug,
    country: o.country,
    currency: o.currency,
    locale: o.locale,
    roles,
    status: 'active',
  };
}

const fechner = org('fechner', 'Fechner GmbH');

export function makeMe(overrides: Partial<Me> = {}): Me {
  return {
    user: { id: 'u1', email: 'estimator@fechner.example', first_name: 'Eva', last_name: 'Schmidt' },
    active_org: fechner,
    memberships: [membership(fechner, ['estimator'])],
    effective_permissions: ['view_all', 'quote_annotate', 'quote_edit', 'quote_finalize'],
    roles: ['estimator'],
    ...overrides,
  };
}

export async function renderWithProviders(
  ui: ReactElement,
  opts: { me?: Me; route?: string } = {},
): Promise<RenderResult> {
  const me = opts.me ?? makeMe();
  // Reset the shared i18n singleton to the session's locale so a prior test's
  // language switch can't leak in (deterministic, order-independent renders).
  // Awaited so the language is applied before the first render — no race.
  await i18n.changeLanguage(localeToLanguage(me.active_org.locale));
  return render(
    <MemoryRouter initialEntries={[opts.route ?? '/']}>
      <I18nextProvider i18n={i18n}>
        <SessionContext.Provider value={me}>{ui}</SessionContext.Provider>
      </I18nextProvider>
    </MemoryRouter>,
  );
}
