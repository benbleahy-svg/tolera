/**
 * Shared quiet stubs for the Found-in-Files panel (M3.2), used by every
 * PdfViewerPage-mounting test that is NOT about the panel itself
 * (the panel's behaviour lives in found-in-files.test.tsx). Plain stable
 * functions — never vi.fn(), so mock resets can't strip them.
 */

/** getPart/getGeometry additions for a `usePartsApi` stableApi mock. */
export const partPanelStubs = {
  getPart: () =>
    Promise.resolve({
      id: 'p1',
      primary_file_id: null,
      name: null,
      part_number: null,
      revision: null,
      description: null,
      archived: false,
      created_at: '',
      updated_at: '',
    }),
  getGeometry: () =>
    Promise.resolve({
      part_id: 'p1',
      size_x: null,
      size_y: null,
      size_z: null,
      max_dim: null,
      med_dim: null,
      min_dim: null,
      area: null,
      volume: null,
      weight: null,
      overrides: {},
    }),
};

/** A full, no-findings `useLensApi` surface. */
export const stableLensApi = {
  listFindings: () => Promise.resolve([]),
  extract: () => Promise.resolve({ task_id: 't' }),
  extractStatus: () =>
    Promise.resolve({ state: 'succeeded', finding_count: 0, dropped_count: 0, error: null }),
  acceptFinding: () => Promise.resolve({ finding: null, applied_field: null }),
  rejectFinding: () => Promise.resolve({ finding: null, applied_field: null }),
  replaceFinding: () => Promise.resolve({ finding: null, applied_field: null }),
  addMissing: () => Promise.resolve(null),
};
