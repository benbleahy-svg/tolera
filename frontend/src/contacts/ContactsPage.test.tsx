import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';

import { makeMe, renderWithProviders } from '../test/render';
import { ContactsPage } from './ContactsPage';

const listAccounts = vi.fn();

// Mock the CRM API module so the page never touches Clerk/network (the test
// render helper is deliberately Clerk-free).
vi.mock('./api', () => ({
  useCrmApi: () => ({ listAccounts }),
}));

function account(name: string, extra: Record<string, unknown> = {}) {
  return {
    id: `acc-${name}`,
    name,
    type: 'customer',
    email: `info@${name}.example`,
    phone: null,
    phone_ext: null,
    website: null,
    notes: null,
    salesperson_id: null,
    archived: false,
    created_at: '2026-06-25T00:00:00Z',
    updated_at: '2026-06-25T00:00:00Z',
    ...extra,
  };
}

describe('ContactsPage', () => {
  beforeEach(() => {
    listAccounts.mockReset();
  });

  it('lists accounts returned by the API', async () => {
    listAccounts.mockResolvedValue([account('Fechner'), account('Acme')]);
    await renderWithProviders(<ContactsPage />, { route: '/contacts' });

    expect(await screen.findByText('Fechner')).toBeInTheDocument();
    expect(screen.getByText('Acme')).toBeInTheDocument();
  });

  it('shows the Create Account action for an editor', async () => {
    listAccounts.mockResolvedValue([]);
    await renderWithProviders(<ContactsPage />); // default makeMe = estimator (quote_edit)

    expect(await screen.findByText('Konto anlegen')).toBeInTheDocument();
  });

  it('hides the Create Account action without quote_edit', async () => {
    listAccounts.mockResolvedValue([]);
    await renderWithProviders(<ContactsPage />, {
      me: makeMe({ effective_permissions: ['view_all'], roles: ['viewer'] }),
    });

    expect(await screen.findByText('Noch keine Konten.')).toBeInTheDocument();
    expect(screen.queryByText('Konto anlegen')).not.toBeInTheDocument();
  });
});
