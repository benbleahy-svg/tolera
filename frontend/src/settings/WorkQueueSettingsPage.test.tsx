import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { WorkQueueSettingsPage } from './WorkQueueSettingsPage';

const getSettings = vi.fn();
const saveSettings = vi.fn();
const api = {
  getSettings,
  saveSettings,
  getQueue: vi.fn(),
  getRecents: vi.fn(),
  recordRecent: vi.fn(),
  getKpis: vi.fn(),
};
vi.mock('../dashboard/workQueueApi', async () => {
  const actual =
    await vi.importActual<typeof import('../dashboard/workQueueApi')>('../dashboard/workQueueApi');
  return { ...actual, useWorkQueueApi: () => api };
});

const DEFAULTS = {
  weight_due: '0.4000',
  weight_value: '0.2500',
  weight_unresolved: '0.2500',
  weight_flags: '0.1000',
  vendor_rfq_queue_enabled: false,
};

describe('WorkQueueSettingsPage (M6.1)', () => {
  beforeEach(() => {
    getSettings.mockReset().mockResolvedValue(DEFAULTS);
    saveSettings.mockReset().mockImplementation((patch) => Promise.resolve({ ...DEFAULTS, ...patch }));
  });

  it('shows the shipped default weights', async () => {
    await renderWithProviders(<WorkQueueSettingsPage />);
    expect(await screen.findByLabelText('Fälligkeit')).toHaveValue(0.4);
    expect(screen.getByLabelText('Auftragswert')).toHaveValue(0.25);
  });

  it('saves a re-weighting', async () => {
    await renderWithProviders(<WorkQueueSettingsPage />);
    const due = await screen.findByLabelText('Fälligkeit');
    await userEvent.clear(due);
    await userEvent.type(due, '0.9');
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }));

    await waitFor(() =>
      expect(saveSettings).toHaveBeenCalledWith(expect.objectContaining({ weight_due: '0.9' })),
    );
    expect(await screen.findByRole('status')).toHaveTextContent('Gespeichert.');
  });

  it('surfaces a translated error instead of a raw failure', async () => {
    getSettings.mockRejectedValue(new Error('boom'));
    await renderWithProviders(<WorkQueueSettingsPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Einstellungen konnten nicht geladen werden.',
    );
  });
});
