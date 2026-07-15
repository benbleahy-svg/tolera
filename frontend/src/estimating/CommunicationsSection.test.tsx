/**
 * Communications timeline on the quote (M3.5): round-trip renders in order
 * (outbound then inbound), the compose box sends via the API, and a missing
 * connection surfaces the connect banner instead of a raw error.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ApiError } from '../api/client';
import { renderWithProviders } from '../test/render';
import { CommunicationsSection } from './CommunicationsSection';
import type { EmailMessage } from '../settings/types';

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

vi.mock('../settings/api', () => ({
  useEmailApi: () => api,
}));

function message(over: Partial<EmailMessage> = {}): EmailMessage {
  return {
    id: 'm-1',
    direction: 'outbound',
    from_address: 'jan@acme-machining.de',
    to_addresses: ['einkauf@kunde.de'],
    subject: 'Ihr Angebot Q-1',
    body_text: 'Anbei unser Angebot.',
    body_html: null,
    attachments: [],
    sent_at: '2026-07-15T09:00:00Z',
    created_at: '2026-07-15T09:00:00Z',
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getQuoteEmails.mockResolvedValue([]);
});

describe('CommunicationsSection', () => {
  it('renders the round-trip in order with direction badges', async () => {
    api.getQuoteEmails.mockResolvedValue([
      message(),
      message({
        id: 'm-2',
        direction: 'inbound',
        from_address: 'einkauf@kunde.de',
        subject: 'AW: Ihr Angebot Q-1',
        body_text: 'Wir bestellen.',
        created_at: '2026-07-15T11:00:00Z',
      }),
    ]);
    renderWithProviders(<CommunicationsSection quoteId="q1" canSend />);
    const entries = await screen.findAllByRole('listitem');
    expect(entries[0]).toHaveAttribute('data-direction', 'outbound');
    expect(entries[1]).toHaveAttribute('data-direction', 'inbound');
    expect(screen.getByText('Gesendet')).toBeInTheDocument();
    expect(screen.getByText('Empfangen')).toBeInTheDocument();
  });

  it('sends a message through the compose box', async () => {
    api.sendQuoteEmail.mockResolvedValue(message());
    renderWithProviders(<CommunicationsSection quoteId="q1" canSend />);
    await userEvent.click(await screen.findByRole('button', { name: 'Nachricht senden' }));
    await userEvent.type(screen.getByLabelText('An'), 'einkauf@kunde.de');
    await userEvent.type(screen.getByLabelText('Betreff'), 'Ihr Angebot');
    await userEvent.type(screen.getByLabelText('Nachricht'), 'Guten Tag');
    await userEvent.click(screen.getByRole('button', { name: 'Senden' }));
    await waitFor(() =>
      expect(api.sendQuoteEmail).toHaveBeenCalledWith('q1', {
        to: ['einkauf@kunde.de'],
        subject: 'Ihr Angebot',
        body_text: 'Guten Tag',
      }),
    );
  });

  it('shows the connect banner when no mailbox is connected', async () => {
    api.sendQuoteEmail.mockRejectedValue(
      new ApiError(409, 'no_email_connection', 'Kein E-Mail-Konto verbunden.'),
    );
    renderWithProviders(<CommunicationsSection quoteId="q1" canSend />);
    await userEvent.click(await screen.findByRole('button', { name: 'Nachricht senden' }));
    await userEvent.type(screen.getByLabelText('An'), 'x@y.de');
    await userEvent.type(screen.getByLabelText('Betreff'), 'B');
    await userEvent.type(screen.getByLabelText('Nachricht'), 'T');
    await userEvent.click(screen.getByRole('button', { name: 'Senden' }));
    expect(await screen.findByText(/Kein E-Mail-Konto verbunden/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Jetzt verbinden' })).toBeInTheDocument();
  });

  it('hides the compose button without edit permission', async () => {
    renderWithProviders(<CommunicationsSection quoteId="q1" canSend={false} />);
    expect(await screen.findByText(/Noch keine E-Mails/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Nachricht senden' })).not.toBeInTheDocument();
  });
});
