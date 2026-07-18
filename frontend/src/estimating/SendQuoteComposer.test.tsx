/**
 * Send-quote composer (M5.5, DemoK/12): adding a CC recipient, picking a template
 * (fills subject + body), toggling the PDF attachment and sending posts the exact
 * `{to, cc, bcc, subject, body_html, include_pdf}` payload; a `no_email_connection`
 * error surfaces the "connect your email" banner.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ApiError } from '../api/client';
import { renderWithProviders } from '../test/render';
import { SendQuoteComposer } from './SendQuoteComposer';
import type { EmailTemplate } from '../settings/types';

const emailApi = {
  sendQuote: vi.fn(),
  previewQuoteSend: vi.fn(),
};
const templatesApi = {
  list: vi.fn(),
  create: vi.fn(),
  get: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
};

vi.mock('../settings/api', () => ({
  useEmailApi: () => emailApi,
  useEmailTemplatesApi: () => templatesApi,
}));

function template(over: Partial<EmailTemplate> = {}): EmailTemplate {
  return {
    id: 'qt-1',
    template_type: 'quote_send',
    name: 'Demo Follow-Up',
    subject: 'Tolera: Beispielangebot',
    body: '<p>Sehr geehrter Herr Martin</p>',
    is_default: false,
    locale: 'de-DE',
    last_edited_by: null,
    updated_at: '2026-07-15T10:00:00Z',
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  templatesApi.list.mockResolvedValue([]);
});

describe('SendQuoteComposer', () => {
  it('sends with the composed recipients, template subject/body and PDF toggle', async () => {
    templatesApi.list.mockResolvedValue([template()]);
    emailApi.sendQuote.mockResolvedValue({
      quote_id: 'q-1',
      status: 'sent',
      recipients: ['sarah@acme.de'],
      pdf_attached: false,
    });
    const onSent = vi.fn();
    const onClose = vi.fn();
    await renderWithProviders(
      <SendQuoteComposer quoteId="q-1" onClose={onClose} onSent={onSent} />,
    );

    // Wait for the template list to load, then compose.
    await screen.findByRole('option', { name: 'Demo Follow-Up' });

    const typeSelect = screen.getByLabelText('Empfängertyp');
    const emailInput = screen.getByLabelText('E-Mail-Adresse des Empfängers');

    // Add the primary To recipient.
    await userEvent.selectOptions(typeSelect, 'to');
    await userEvent.type(emailInput, 'chris@kunde.de');
    await userEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }));

    // Add a CC recipient.
    await userEvent.selectOptions(typeSelect, 'cc');
    await userEvent.type(emailInput, 'sarah@acme.de');
    await userEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }));

    // Pick the template — fills subject + body.
    await userEvent.selectOptions(
      screen.getByLabelText('E-Mail-Vorlage auswählen'),
      'qt-1',
    );
    expect(screen.getByLabelText('Betreff')).toHaveValue('Tolera: Beispielangebot');

    // Uncheck the (default-on) PDF attachment.
    await userEvent.click(screen.getByLabelText('Angebot als PDF anhängen'));

    await userEvent.click(screen.getByRole('button', { name: 'Angebot senden' }));

    await waitFor(() =>
      expect(emailApi.sendQuote).toHaveBeenCalledWith('q-1', {
        to: ['chris@kunde.de'],
        cc: ['sarah@acme.de'],
        bcc: [],
        template_id: 'qt-1',
        subject: 'Tolera: Beispielangebot',
        body_html: '<p>Sehr geehrter Herr Martin</p>',
        include_pdf: false,
      }),
    );
    await waitFor(() => expect(onSent).toHaveBeenCalled());
  });

  it('disables preview + send until a To recipient is added', async () => {
    await renderWithProviders(
      <SendQuoteComposer quoteId="q-1" onClose={vi.fn()} onSent={vi.fn()} />,
    );
    // No recipients yet → both actions disabled.
    expect(screen.getByRole('button', { name: 'Vorschau' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Angebot senden' })).toBeDisabled();

    // A CC alone does not satisfy the To requirement.
    await userEvent.selectOptions(screen.getByLabelText('Empfängertyp'), 'cc');
    await userEvent.type(screen.getByLabelText('E-Mail-Adresse des Empfängers'), 'cc@kunde.de');
    await userEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }));
    expect(screen.getByRole('button', { name: 'Angebot senden' })).toBeDisabled();

    // Adding a To recipient enables both.
    await userEvent.selectOptions(screen.getByLabelText('Empfängertyp'), 'to');
    await userEvent.type(screen.getByLabelText('E-Mail-Adresse des Empfängers'), 'chris@kunde.de');
    await userEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }));
    expect(screen.getByRole('button', { name: 'Angebot senden' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Vorschau' })).toBeEnabled();
  });

  it('shows the connect-email banner on no_email_connection', async () => {
    emailApi.sendQuote.mockRejectedValue(
      new ApiError(409, 'no_email_connection', 'connect first'),
    );
    await renderWithProviders(
      <SendQuoteComposer quoteId="q-1" onClose={vi.fn()} onSent={vi.fn()} />,
    );
    // A To recipient is required before send is enabled.
    await userEvent.selectOptions(screen.getByLabelText('Empfängertyp'), 'to');
    await userEvent.type(screen.getByLabelText('E-Mail-Adresse des Empfängers'), 'chris@kunde.de');
    await userEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }));
    await userEvent.click(screen.getByRole('button', { name: 'Angebot senden' }));
    expect(await screen.findByRole('link', { name: 'Jetzt verbinden' })).toBeInTheDocument();
  });
});
