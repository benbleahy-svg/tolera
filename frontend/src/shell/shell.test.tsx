import { beforeEach, describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import i18n from '../i18n';
import { makeMe, membership, org, renderWithProviders } from '../test/render';
import { Sidebar } from './Sidebar';

beforeEach(async () => {
  localStorage.clear();
  await i18n.changeLanguage('de');
});

describe('role-aware navigation', () => {
  it('hides Configure for a user without config_edit', async () => {
    await renderWithProviders(<Sidebar />, {
      me: makeMe({ effective_permissions: ['view_all', 'quote_edit'] }),
    });
    // Dashboard is always present...
    expect(screen.getByRole('link', { name: 'Übersicht' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Angebote' })).toBeInTheDocument();
    // ...but Configure requires config_edit.
    expect(screen.queryByRole('link', { name: 'Konfiguration' })).not.toBeInTheDocument();
  });

  it('shows Configure for an admin (has config_edit)', async () => {
    await renderWithProviders(<Sidebar />, {
      me: makeMe({ effective_permissions: ['view_all', 'config_edit'] }),
    });
    expect(screen.getByRole('link', { name: 'Konfiguration' })).toBeInTheDocument();
  });
});

describe('i18n locale toggle', () => {
  it('swaps the catalog live (de → en)', async () => {
    const user = userEvent.setup();
    await renderWithProviders(<Sidebar />);

    // German by default (de-DE pilot default).
    expect(screen.getByRole('link', { name: 'Übersicht' })).toBeInTheDocument();

    // Open the account menu and switch to English.
    await user.click(screen.getByRole('button', { name: 'Konto' }));
    await user.click(screen.getByRole('button', { name: 'EN' }));

    // Strings re-render in English; the German ones are gone.
    expect(await screen.findByRole('link', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Übersicht' })).not.toBeInTheDocument();
  });
});

describe('org-switcher (M0.4 stub)', () => {
  it('lists every membership and marks the active org; others are not switchable yet', async () => {
    const user = userEvent.setup();
    const fechner = org('fechner', 'Fechner GmbH');
    const helvetia = org('helvetia', 'Helvetia AG', { country: 'CH', currency: 'CHF', locale: 'de-CH' });
    const me = makeMe({
      active_org: fechner,
      memberships: [membership(fechner, ['estimator']), membership(helvetia, ['viewer'])],
    });
    await renderWithProviders(<Sidebar />, { me });

    await user.click(screen.getByRole('button', { name: 'Konto' }));

    const switcher = screen.getByRole('group', { name: 'Organisation' });
    expect(within(switcher).getByText('Fechner GmbH')).toBeInTheDocument();
    expect(within(switcher).getByText('Helvetia AG')).toBeInTheDocument();

    // The active org is current; switching to the other is deferred to M5.12.
    const active = within(switcher).getByRole('button', { name: /Fechner GmbH/ });
    const other = within(switcher).getByRole('button', { name: /Helvetia AG/ });
    expect(active).toHaveAttribute('aria-current', 'true');
    expect(other).toBeDisabled();
  });
});
