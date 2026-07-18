/**
 * Settings → Email Templates (M5.5, DemoH/08): the three sections render, a new
 * template is created via the editor modal, and a `default_template_protected`
 * 409 on delete surfaces the German guard message.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ApiError } from '../api/client';
import { renderWithProviders } from '../test/render';
import { EmailTemplatesPage } from './EmailTemplatesPage';
import type { EmailTemplate } from './types';

const api = {
  list: vi.fn(),
  create: vi.fn(),
  get: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
};

vi.mock('./api', () => ({
  useEmailTemplatesApi: () => api,
}));

function template(over: Partial<EmailTemplate> = {}): EmailTemplate {
  return {
    id: 't-1',
    template_type: 'quote_send',
    name: 'Standard-Angebot',
    subject: 'Ihr Angebot',
    body: 'Sehr geehrte Damen und Herren',
    is_default: false,
    locale: 'de-DE',
    last_edited_by: 'eva@fechner.example',
    updated_at: '2026-07-15T10:00:00Z',
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.list.mockResolvedValue([]);
});

describe('EmailTemplatesPage', () => {
  it('renders the three template sections', async () => {
    await renderWithProviders(<EmailTemplatesPage />);
    expect(await screen.findByText('Angebots-E-Mails')).toBeInTheDocument();
    expect(screen.getByText('Versand-E-Mails')).toBeInTheDocument();
    expect(screen.getByText('Erstattungs-E-Mails')).toBeInTheDocument();
  });

  it('creates a new quote-send template via the editor modal', async () => {
    api.create.mockResolvedValue(template());
    await renderWithProviders(<EmailTemplatesPage />);
    await userEvent.click(
      await screen.findByRole('button', { name: 'Neue Angebotsvorlage erstellen' }),
    );
    await userEvent.type(screen.getByLabelText('Name'), 'Follow-Up');
    await userEvent.type(screen.getByLabelText('Betreff'), 'Ihr Angebot');
    await userEvent.type(screen.getByLabelText('Nachricht'), 'Guten Tag');
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    await waitFor(() =>
      expect(api.create).toHaveBeenCalledWith(
        expect.objectContaining({
          template_type: 'quote_send',
          name: 'Follow-Up',
          subject: 'Ihr Angebot',
          body: 'Guten Tag',
        }),
      ),
    );
  });

  it('surfaces the default-protected error when a delete is rejected', async () => {
    api.list.mockResolvedValue([template({ id: 't-9', name: 'Zu löschen' })]);
    api.remove.mockRejectedValue(
      new ApiError(409, 'default_template_protected', 'protected'),
    );
    await renderWithProviders(<EmailTemplatesPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Löschen' }));
    expect(
      await screen.findByText('Die Standardvorlage kann nicht gelöscht werden.'),
    ).toBeInTheDocument();
  });

  it('greys out delete on the default row', async () => {
    api.list.mockResolvedValue([template({ id: 't-def', is_default: true })]);
    await renderWithProviders(<EmailTemplatesPage />);
    const deleteBtn = await screen.findByRole('button', { name: 'Löschen' });
    expect(deleteBtn).toBeDisabled();
  });
});
