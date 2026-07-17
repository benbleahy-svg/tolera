/**
 * Configure → Interrogations (M4.7/M4.8, spec #interrogations-config): the
 * DFM profile page — catalogue rows with toggles + thresholds, always-on rows
 * locked, v2/Spatial rows badged, a save that PUTs only allowed inputs; plus
 * the M4.8 authoring surface — create/delete named profiles, material +
 * operation-def link editors, and the advisory duplicate-dispatch ⚠️.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { InterrogationsPage } from './InterrogationsPage';
import type { InterrogationProfileOut, InterrogationsConfigOut } from './api';

const getInterrogationsConfig = vi.fn();
const updateInterrogationProfile = vi.fn();
const createInterrogationProfile = vi.fn();
const deleteInterrogationProfile = vi.fn();
const listOperationDefs = vi.fn();
const materialTree = vi.fn();

const apiMock = {
  getInterrogationsConfig,
  updateInterrogationProfile,
  createInterrogationProfile,
  deleteInterrogationProfile,
  listOperationDefs,
};
vi.mock('./api', () => ({
  useConfigureApi: () => apiMock,
}));
vi.mock('../estimating/api', () => ({
  useEstimatingApi: () => ({ materialTree }),
}));

const DEFAULT_PROFILE: InterrogationProfileOut = {
  id: 'prof-1',
  name: 'Standard CNC-Fräsen',
  family: 'MILLING',
  is_default: true,
  inputs: {
    deep_hole_ratio_threshold: 8,
    should_detect_deep_hole: true,
    should_detect_tapered_walls: true,
  },
  material_class_id: null,
  material_family_id: null,
  material_id: null,
  operation_def_ids: [],
};

const VARIANT_PROFILE: InterrogationProfileOut = {
  ...DEFAULT_PROFILE,
  id: 'prof-2',
  name: 'CNC-Fräsen Aluminium',
  is_default: false,
  inputs: { ...DEFAULT_PROFILE.inputs, deep_hole_ratio_threshold: 20 },
  material_family_id: 'fam-alu',
};

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
  profiles: [DEFAULT_PROFILE, VARIANT_PROFILE],
};

const MATERIAL_TREE = [
  {
    id: 'cls-metal',
    name: 'Metall',
    families: [
      {
        id: 'fam-alu',
        name: 'Aluminium',
        alias: 'Aluminum',
        materials: [{ id: 'mat-6061', family_id: 'fam-alu', display_name: 'EN AW-6061' }],
      },
      {
        id: 'fam-inox',
        name: 'Nichtrostender Stahl',
        alias: 'Stainless steel',
        materials: [{ id: 'mat-4301', family_id: 'fam-inox', display_name: '1.4301' }],
      },
    ],
  },
];

const OP_DEFS = [
  { id: 'op-mill', name: 'CNC Mill' },
  { id: 'op-saw', name: 'Saw' },
];

function variantSection() {
  const heading = screen.getByText(/CNC-Fräsen Aluminium/);
  const section = heading.closest('section');
  if (section == null) throw new Error('variant section not rendered');
  return within(section);
}

beforeEach(() => {
  getInterrogationsConfig.mockReset();
  updateInterrogationProfile.mockReset();
  createInterrogationProfile.mockReset();
  deleteInterrogationProfile.mockReset();
  listOperationDefs.mockReset();
  materialTree.mockReset();
  getInterrogationsConfig.mockResolvedValue(CONFIG);
  listOperationDefs.mockResolvedValue(OP_DEFS);
  materialTree.mockResolvedValue(MATERIAL_TREE);
});

describe('InterrogationsPage', () => {
  it('renders catalogue rows: locked always-on, v2/Spatial badge, thresholds', async () => {
    await renderWithProviders(<InterrogationsPage />);
    await waitFor(() => {
      expect(
        screen.getByRole('heading', { level: 1, name: 'Interrogationen' }),
      ).toBeInTheDocument();
    });
    // family section with the seeded profile name + default badge
    expect(screen.getAllByText(/Fräsen/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Standard CNC-Fräsen/)).toBeInTheDocument();
    expect(screen.getByText('Standard')).toBeInTheDocument();
    // localized warning names (one row per profile section)
    expect(screen.getAllByText('Tiefe Bohrung').length).toBe(2);
    // always-on row: disabled checked checkbox + badge
    const alwaysOn = screen.getAllByLabelText(/Nicht zerspanbare Flächen Immer aktiv/)[0];
    expect(alwaysOn).toBeChecked();
    expect(alwaysOn).toBeDisabled();
    // v2/Spatial badge on the unsupported row
    expect(screen.getAllByText('v2/Spatial').length).toBe(2);
    // threshold inputs carry each profile's own value
    expect(screen.getByLabelText('Standard CNC-Fräsen deep_hole_ratio_threshold')).toHaveValue(8);
    expect(screen.getByLabelText('CNC-Fräsen Aluminium deep_hole_ratio_threshold')).toHaveValue(
      20,
    );
  });

  it('saves edited toggles + thresholds via PUT (M4.7 acceptance)', async () => {
    updateInterrogationProfile.mockImplementation(
      (_id: string, body: { inputs: Record<string, number | boolean> }) =>
        Promise.resolve({ ...DEFAULT_PROFILE, inputs: body.inputs, warnings: [] }),
    );
    await renderWithProviders(<InterrogationsPage />);
    await waitFor(() => {
      expect(screen.getAllByText('Tiefe Bohrung').length).toBe(2);
    });
    await userEvent.click(screen.getAllByLabelText(/Tiefe Bohrung Aktiv/)[0]);
    const threshold = screen.getByLabelText('Standard CNC-Fräsen deep_hole_ratio_threshold');
    await userEvent.clear(threshold);
    await userEvent.type(threshold, '12.5');
    await userEvent.click(screen.getAllByRole('button', { name: 'Speichern' })[0]);
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('Gespeichert.');
    });
    expect(updateInterrogationProfile).toHaveBeenCalledWith('prof-1', {
      inputs: expect.objectContaining({
        should_detect_deep_hole: false,
        deep_hole_ratio_threshold: 12.5,
      }) as Record<string, number | boolean>,
    });
    // never invents a toggle for the always-on warning
    const sent = (
      updateInterrogationProfile.mock.calls[0][1] as {
        inputs: Record<string, unknown>;
      }
    ).inputs;
    expect('should_detect_uncut_faces' in sent).toBe(false);
  });

  it('shows the link editor only on variants and saves a material-family link', async () => {
    updateInterrogationProfile.mockResolvedValue({
      ...VARIANT_PROFILE,
      material_family_id: 'fam-inox',
      warnings: [],
    });
    await renderWithProviders(<InterrogationsPage />);
    await waitFor(() => {
      expect(screen.getByText(/CNC-Fräsen Aluminium/)).toBeInTheDocument();
    });
    // exactly one link editor (the variant's) — the default has none
    expect(screen.getAllByLabelText(/Werkstofffamilie/).length).toBe(1);
    const familySelect = variantSection().getByLabelText(/Werkstofffamilie/);
    expect(familySelect).toHaveValue('fam-alu');
    await userEvent.selectOptions(familySelect, 'fam-inox');
    await waitFor(() => {
      expect(updateInterrogationProfile).toHaveBeenCalledWith('prof-2', {
        material_family_id: 'fam-inox',
      });
    });
  });

  it('surfaces the advisory duplicate-dispatch ⚠️ after an op-link save', async () => {
    updateInterrogationProfile.mockResolvedValue({
      ...VARIANT_PROFILE,
      operation_def_ids: ['op-mill'],
      warnings: [
        {
          code: 'duplicate_dispatch',
          process_id: 'proc-1',
          process_name: 'CNC-Fräsen',
          other_profile_id: 'prof-3',
          other_profile_name: 'Fräsen B',
        },
      ],
    });
    await renderWithProviders(<InterrogationsPage />);
    await waitFor(() => {
      expect(screen.getByText(/CNC-Fräsen Aluminium/)).toBeInTheDocument();
    });
    await userEvent.selectOptions(variantSection().getByLabelText(/Arbeitsgänge/), 'op-mill');
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/Fräsen B/);
      expect(screen.getByRole('alert')).toHaveTextContent(/doppelt/);
    });
  });

  it('creates a named profile per family and deletes only variants', async () => {
    createInterrogationProfile.mockResolvedValue({
      ...DEFAULT_PROFILE,
      id: 'prof-new',
      name: 'Fräsen Messing',
      is_default: false,
    });
    deleteInterrogationProfile.mockResolvedValue(undefined);
    await renderWithProviders(<InterrogationsPage />);
    await waitFor(() => {
      expect(screen.getByText(/CNC-Fräsen Aluminium/)).toBeInTheDocument();
    });
    // the default section has no delete button; the variant has one
    expect(screen.getAllByRole('button', { name: 'Profil löschen' }).length).toBe(1);

    await userEvent.type(screen.getByLabelText(/Profilname/), 'Fräsen Messing');
    await userEvent.click(screen.getByRole('button', { name: /Neues Profil/ }));
    await waitFor(() => {
      expect(createInterrogationProfile).toHaveBeenCalledWith('Fräsen Messing', 'MILLING');
      expect(screen.getByText(/Fräsen Messing/)).toBeInTheDocument();
    });

    await userEvent.click(screen.getAllByRole('button', { name: 'Profil löschen' })[0]);
    await waitFor(() => {
      expect(deleteInterrogationProfile).toHaveBeenCalled();
    });
  });
});
