/**
 * Settings → Finalized Quote Settings (M5.8): the page loads the org's settings,
 * a toggled Display Setting + a disabled shipping method are sent on save, and
 * the German copy renders. The API hook is mocked wholesale (the EmailTemplates
 * pattern).
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { QuoteSettingsPage } from './QuoteSettingsPage';
import type { QuoteSettings } from './quoteSettings';

const api = {
  get: vi.fn(),
  update: vi.fn(),
};

vi.mock('./quoteSettings', async () => {
  const actual = await vi.importActual<typeof import('./quoteSettings')>('./quoteSettings');
  return { ...actual, useQuoteSettingsApi: () => api };
});

function settings(over: Partial<QuoteSettings> = {}): QuoteSettings {
  return {
    show_part_number: true,
    show_revision: true,
    show_description: true,
    show_process: true,
    show_material: true,
    show_dimensions: false,
    show_dfm: false,
    show_3d: true,
    show_part_file_name: false,
    show_thumbnail: false,
    show_quote_number: true,
    show_rfq_number: true,
    show_facility_phone: true,
    show_facility_website: true,
    show_digital_quote_link: true,
    total_display: 'price_range',
    preparer: 'salesperson',
    notes_placement: 'above',
    terms: null,
    manufacturers_notes: null,
    quote_notes: null,
    require_terms_acceptance: false,
    requotes_enabled: true,
    allow_local_pickup: true,
    send_order_confirmation_emails: true,
    disabled_shipping_methods: [],
    lead_time_business_days: true,
    notification_recipients: {},
    default_tax_rate_pct: null,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockResolvedValue(settings());
  api.update.mockImplementation((body) => Promise.resolve(settings(body)));
});

describe('QuoteSettingsPage', () => {
  it('renders the settings groups in German', async () => {
    await renderWithProviders(<QuoteSettingsPage />);
    expect(
      await screen.findByRole('heading', { name: 'Einstellungen für finalisierte Angebote' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Anzeigeeinstellungen für Angebote')).toBeInTheDocument();
    expect(screen.getByText('Checkout-Einstellungen')).toBeInTheDocument();
    expect(screen.getByLabelText('Werkstoff')).toBeChecked();
  });

  it('sends a toggled Display Setting and a disabled method on save', async () => {
    const user = userEvent.setup();
    await renderWithProviders(<QuoteSettingsPage />);
    await screen.findByLabelText('Werkstoff');

    // Turn OFF the material display toggle.
    await user.click(screen.getByLabelText('Werkstoff'));
    // Uncheck "Keine Versandkosten" (offered) → it becomes a disabled method.
    await user.click(screen.getByLabelText('Keine Versandkosten'));
    await user.click(screen.getByRole('button', { name: 'Speichern' }));

    await waitFor(() => expect(api.update).toHaveBeenCalledTimes(1));
    // Partial-update contract: ONLY the two touched fields are sent, not the
    // whole draft — so a concurrent admin's untouched settings aren't clobbered.
    expect(api.update).toHaveBeenCalledWith({
      show_material: false,
      disabled_shipping_methods: ['no_shipping_fees'],
    });
    expect(await screen.findByText('Gespeichert')).toBeInTheDocument();
  });

  it('turns the Requotes toggle off', async () => {
    const user = userEvent.setup();
    await renderWithProviders(<QuoteSettingsPage />);
    const requotes = await screen.findByLabelText(
      'Käufern erlauben, aus dem digitalen Angebot eine Aktualisierung anzufordern',
    );
    expect(requotes).toBeChecked();
    await user.click(requotes);
    await user.click(screen.getByRole('button', { name: 'Speichern' }));

    await waitFor(() => expect(api.update).toHaveBeenCalledTimes(1));
    expect(api.update).toHaveBeenCalledWith({ requotes_enabled: false });
  });
});
