/**
 * Settings → Email Connection (M3.5, spec #email-connectivity): connect
 * buttons, the manual SMTP/IMAP form, connection status (from-address,
 * primary badge, last synced), test-send and disconnect. German-first copy.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { EmailConnectionPage } from './EmailConnectionPage';
import type { EmailConnection } from './types';

const api = {
  listConnections: vi.fn(),
  connectSmtp: vi.fn(),
  disconnect: vi.fn(),
  setPrimary: vi.fn(),
  testConnection: vi.fn(),
  oauthStart: vi.fn(),
  getQuoteEmails: vi.fn(),
  sendQuoteEmail: vi.fn(),
};

vi.mock('./api', () => ({
  useEmailApi: () => api,
}));

function connection(over: Partial<EmailConnection> = {}): EmailConnection {
  return {
    id: 'c-1',
    connection_type: 'smtp_imap',
    from_address: 'jan@acme-machining.de',
    from_name: 'Jan Fechner',
    is_primary: true,
    last_synced_at: '2026-07-15T10:00:00Z',
    last_sync_error: null,
    created_at: '2026-07-01T08:00:00Z',
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listConnections.mockResolvedValue([]);
});

describe('EmailConnectionPage', () => {
  it('shows the connected account with primary badge and sync status', async () => {
    api.listConnections.mockResolvedValue([connection()]);
    renderWithProviders(<EmailConnectionPage />);
    expect(await screen.findByText('jan@acme-machining.de')).toBeInTheDocument();
    expect(screen.getByText('Primär')).toBeInTheDocument();
    expect(screen.getByText(/Zuletzt synchronisiert/)).toBeInTheDocument();
  });

  it('submits the manual SMTP/IMAP form', async () => {
    api.connectSmtp.mockResolvedValue(connection());
    renderWithProviders(<EmailConnectionPage />);
    await userEvent.click(await screen.findByRole('button', { name: /Manuell/ }));
    await userEvent.type(screen.getByLabelText('Absenderadresse'), 'jan@acme-machining.de');
    await userEvent.type(screen.getByLabelText('SMTP-Server'), 'smtp.acme.de');
    await userEvent.type(screen.getByLabelText('IMAP-Server'), 'imap.acme.de');
    await userEvent.type(screen.getByLabelText('Benutzername'), 'jan');
    await userEvent.type(screen.getByLabelText('Passwort'), 'geheim');
    await userEvent.click(screen.getByRole('button', { name: 'Verbindung speichern' }));
    await waitFor(() =>
      expect(api.connectSmtp).toHaveBeenCalledWith(
        expect.objectContaining({
          from_address: 'jan@acme-machining.de',
          smtp_host: 'smtp.acme.de',
          imap_host: 'imap.acme.de',
          username: 'jan',
          password: 'geheim',
        }),
      ),
    );
  });

  it('starts the Gmail OAuth flow via the authorize URL', async () => {
    api.oauthStart.mockResolvedValue({ authorize_url: 'https://accounts.google.com/x' });
    const assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
    renderWithProviders(<EmailConnectionPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Mit Gmail verbinden' }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith('https://accounts.google.com/x'));
    vi.unstubAllGlobals();
  });

  it('sends the test message and confirms in German', async () => {
    api.listConnections.mockResolvedValue([connection()]);
    api.testConnection.mockResolvedValue({ status: 'sent', subject: 'Test' });
    renderWithProviders(<EmailConnectionPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Verbindung testen' }));
    expect(await screen.findByText(/Testnachricht an die eigene Adresse/)).toBeInTheDocument();
    expect(api.testConnection).toHaveBeenCalledWith('c-1');
  });
});
