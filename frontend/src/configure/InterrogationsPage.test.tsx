/**
 * Configure → Interrogations (M4.7, spec #interrogations-config): the DFM
 * profile page — catalogue rows with toggles + thresholds, always-on rows
 * locked, v2/Spatial rows badged, and a save that PUTs only allowed inputs.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { InterrogationsPage } from './InterrogationsPage';
import type { InterrogationsConfigOut } from './api';

const getInterrogationsConfig = vi.fn();
const updateInterrogationProfile = vi.fn();

const apiMock = { getInterrogationsConfig, updateInterrogationProfile };
vi.mock('./api', () => ({
  useConfigureApi: () => apiMock,
}));

const CONFIG: InterrogationsConfigOut = {
  catalog: [
    {
      family: 'MILLING',
      warnings: [
        {
          type: 'deep_hole',
          detects: 'Cut-depth to hole-diameter ratio too high',
          threshold_fields: ['deep_hole_ratio_threshold'],
          toggle: 'should_detect_deep_hole',
          toggle_default: true,
          v1_supported: true,
          always_on: false,
        },
        {
          type: 'uncut_faces',
          detects: 'Faces inaccessible to 3-axis tooling',
          threshold_fields: [],
          toggle: null,
          toggle_default: true,
          v1_supported: true,
          always_on: true,
        },
        {
          type: 'tapered_walls',
          detects: 'Slanted plane needing surfacing',
          threshold_fields: [],
          toggle: 'should_detect_tapered_walls',
          toggle_default: true,
          v1_supported: false,
          always_on: false,
        },
      ],
      defaults: {
        deep_hole_ratio_threshold: 8,
        should_detect_deep_hole: true,
        should_detect_tapered_walls: true,
      },
    },
  ],
  profiles: [
    {
      id: 'prof-1',
      name: 'Default CNC Milling',
      family: 'MILLING',
      inputs: {
        deep_hole_ratio_threshold: 8,
        should_detect_deep_hole: true,
        should_detect_tapered_walls: true,
      },
    },
  ],
};

beforeEach(() => {
  getInterrogationsConfig.mockReset();
  updateInterrogationProfile.mockReset();
});

describe('InterrogationsPage', () => {
  it('renders catalogue rows: locked always-on, v2/Spatial badge, thresholds', async () => {
    getInterrogationsConfig.mockResolvedValue(CONFIG);
    await renderWithProviders(<InterrogationsPage />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: 'Interrogationen' })).toBeInTheDocument();
    });
    // family section with the seeded profile name
    expect(screen.getByText(/Fräsen/)).toBeInTheDocument();
    expect(screen.getByText(/Default CNC Milling/)).toBeInTheDocument();
    // localized warning names
    expect(screen.getByText('Tiefe Bohrung')).toBeInTheDocument();
    // always-on row: disabled checked checkbox + badge
    const alwaysOn = screen.getByLabelText(/uncut_faces Immer aktiv/);
    expect(alwaysOn).toBeChecked();
    expect(alwaysOn).toBeDisabled();
    expect(screen.getByText('Immer aktiv')).toBeInTheDocument();
    // v2/Spatial badge on the unsupported row
    expect(screen.getByText('v2/Spatial')).toBeInTheDocument();
    // threshold input carries the metric default
    expect(screen.getByLabelText('deep_hole_ratio_threshold')).toHaveValue(8);
  });

  it('saves edited toggles + thresholds via PUT (M4.7 acceptance)', async () => {
    getInterrogationsConfig.mockResolvedValue(CONFIG);
    updateInterrogationProfile.mockImplementation((id: string, inputs: unknown) =>
      Promise.resolve({ ...CONFIG.profiles[0], inputs }),
    );
    await renderWithProviders(<InterrogationsPage />);
    await waitFor(() => {
      expect(screen.getByText('Tiefe Bohrung')).toBeInTheDocument();
    });
    await userEvent.click(screen.getByLabelText(/deep_hole Aktiv/));
    const threshold = screen.getByLabelText('deep_hole_ratio_threshold');
    await userEvent.clear(threshold);
    await userEvent.type(threshold, '12.5');
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('Gespeichert.');
    });
    expect(updateInterrogationProfile).toHaveBeenCalledWith(
      'prof-1',
      expect.objectContaining({
        should_detect_deep_hole: false,
        deep_hole_ratio_threshold: 12.5,
      }),
    );
    // never invents a toggle for the always-on warning
    const sent = updateInterrogationProfile.mock.calls[0][1] as Record<string, unknown>;
    expect('should_detect_uncut_faces' in sent).toBe(false);
  });
});
