/**
 * M3.2 Found-in-Files panel — the AI-Governor gates in executable form:
 * a suggested finding renders translucent (55 % via `data-status`) and writes
 * NOTHING until the explicit Accept calls the backend; mark-inaccurate /
 * replace hit the correction endpoints; whiteout toggles emit the section's
 * finding regions for the M2.4 overlay. APIs are mocked at the module
 * boundary (the PartsPage precedent).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { FoundInFilesPanel } from './FoundInFilesPanel';
import {
  AI_SIGNAL_CONFIDENCE_MIN,
  fillSuggestion,
  findingsBadgeCount,
  groupFindings,
  whiteoutSectionsFor,
  type Finding,
} from './lens';

const listFindings = vi.fn();
const acceptFinding = vi.fn();
const rejectFinding = vi.fn();
const replaceFinding = vi.fn();
const addMissing = vi.fn();
const extract = vi.fn();
const extractStatus = vi.fn();

vi.mock('./lens-api', () => ({
  useLensApi: () => ({
    listFindings,
    extract,
    extractStatus,
    acceptFinding,
    rejectFinding,
    replaceFinding,
    addMissing,
  }),
}));

const getPart = vi.fn();
const updatePart = vi.fn();
const getGeometry = vi.fn();
const updateGeometry = vi.fn();

vi.mock('../parts/api', () => ({
  usePartsApi: () => ({ getPart, updatePart, getGeometry, updateGeometry }),
}));

function finding(extra: Partial<Finding> = {}): Finding {
  return {
    id: 'f1',
    source_file_id: 'file-1',
    component_id: null,
    page: 1,
    category: 'quote_setup',
    type: 'part_number',
    raw_text: 'PP-1212-006',
    value: 'PP-1212-006',
    normalized_value: null,
    units: null,
    tolerance: null,
    role: null,
    gdt: null,
    bbox: { x: 10, y: 20, width: 80, height: 12 },
    confidence: 0.93,
    status: 'suggested',
    ...extra,
  };
}

const PART = {
  id: 'part-1',
  primary_file_id: null,
  name: null,
  part_number: null,
  revision: null,
  description: null,
  archived: false,
  created_at: '',
  updated_at: '',
};

beforeEach(() => {
  vi.clearAllMocks();
  getPart.mockResolvedValue(PART);
  getGeometry.mockResolvedValue({ part_id: 'part-1', size_x: null, size_y: null, size_z: null });
  acceptFinding.mockResolvedValue({ finding: finding({ status: 'accepted' }), applied_field: null });
  rejectFinding.mockResolvedValue({ finding: finding({ status: 'rejected' }), applied_field: null });
  replaceFinding.mockResolvedValue({ finding: finding({ status: 'edited' }), applied_field: null });
});

async function renderPanel(findings: Finding[], onLensWhiteoutsChange?: (s: unknown[]) => void) {
  listFindings.mockResolvedValue(findings);
  await renderWithProviders(
    <FoundInFilesPanel
      partId="part-1"
      fileId="file-1"
      filename="print.pdf"
      onLensWhiteoutsChange={onLensWhiteoutsChange}
    />,
  );
  await waitFor(() => expect(listFindings).toHaveBeenCalled());
}

describe('FoundInFilesPanel — AI-Governor gates', () => {
  it('renders a suggested finding as a translucent chip and writes nothing', async () => {
    await renderPanel([finding()]);
    const chip = await screen.findByRole('button', { name: /PP-1212-006/ });
    // 55 % opacity is keyed off data-status (styles/lens.css).
    expect(chip).toHaveAttribute('data-status', 'suggested');
    // The suggestion alone never touches the part.
    expect(acceptFinding).not.toHaveBeenCalled();
    expect(updatePart).not.toHaveBeenCalled();
  });

  it('explicit Accept calls the atomic accept endpoint (click-to-fill)', async () => {
    await renderPanel([finding()]);
    await userEvent.click(await screen.findByRole('button', { name: /PP-1212-006/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Übernehmen' }));
    await waitFor(() =>
      expect(acceptFinding).toHaveBeenCalledWith('part-1', 'file-1', 'f1', undefined),
    );
    // The part field write happens server-side in the same transaction —
    // the client never PATCHes the part itself from a suggestion.
    expect(updatePart).not.toHaveBeenCalled();
  });

  it('a dimension finding offers the X/Y/Z axis picker', async () => {
    await renderPanel([
      finding({ id: 'f9', category: 'dimensions', type: 'length', value: '3.500', units: 'in' }),
    ]);
    await userEvent.click(await screen.findByRole('button', { name: /3\.500/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Y' }));
    await waitFor(() =>
      expect(acceptFinding).toHaveBeenCalledWith('part-1', 'file-1', 'f9', 'size_y'),
    );
  });

  it('"Als ungenau markieren" hits the reject (training-label) endpoint', async () => {
    await renderPanel([finding()]);
    await userEvent.click(await screen.findByRole('button', { name: /PP-1212-006/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Als ungenau markieren' }));
    await waitFor(() => expect(rejectFinding).toHaveBeenCalledWith('part-1', 'file-1', 'f1'));
  });

  it('replace sends the corrected value', async () => {
    await renderPanel([finding()]);
    await userEvent.click(await screen.findByRole('button', { name: /PP-1212-006/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Ersetzen' }));
    await userEvent.clear(screen.getByLabelText('Neuer Wert')); // prefilled with the current value
    await userEvent.type(screen.getByLabelText('Neuer Wert'), 'PP-1212-007');
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    await waitFor(() =>
      expect(replaceFinding).toHaveBeenCalledWith('part-1', 'file-1', 'f1', 'PP-1212-007'),
    );
  });

  it('whiteout toggle emits the section regions for the M2.4 overlay', async () => {
    const onChange = vi.fn();
    await renderPanel([finding()], onChange);
    const section = (await screen.findByRole('heading', { name: 'Angebotsdaten' }))
      .closest('section') as HTMLElement;
    await userEvent.click(within(section).getByRole('checkbox'));
    await waitFor(() =>
      expect(onChange).toHaveBeenLastCalledWith([
        { id: 'lens-f1', page: 1, rect: { x: 10, y: 20, width: 80, height: 12 } },
      ]),
    );
  });

  it('add-missing posts the typed callout (false-negative label)', async () => {
    addMissing.mockResolvedValue(finding({ id: 'new', status: 'accepted' }));
    await renderPanel([finding()]);
    await userEvent.click(await screen.findByRole('button', { name: 'Fehlende Extraktion hinzufügen' }));
    await userEvent.type(screen.getByLabelText('Typ'), 'process_keywords');
    await userEvent.type(screen.getByLabelText('Wert'), 'passivieren');
    await userEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }));
    await waitFor(() =>
      expect(addMissing).toHaveBeenCalledWith('part-1', 'file-1', {
        category: 'requirements',
        type: 'process_keywords',
        value: 'passivieren',
      }),
    );
  });
});

describe('lens model (pure)', () => {
  it('groups by section and collapses duplicate values with a count', () => {
    const findings = [
      finding({ id: 'a', category: 'dimensions', type: 'angle', value: '90' }),
      finding({ id: 'b', category: 'dimensions', type: 'angle', value: '90' }),
      finding({ id: 'c', category: 'dimensions', type: 'length', value: '3.500' }),
      finding({ id: 'd' }),
    ];
    const sections = groupFindings(findings);
    expect(sections.map((s) => s.key)).toEqual(['quote_setup', 'dimensions']);
    const dims = sections[1];
    expect(dims.groups.map((g) => g.key)).toEqual(['lengths', 'angles']);
    const angleChips = dims.groups[1].chips;
    expect(angleChips).toHaveLength(1);
    expect(angleChips[0].count).toBe(2);
    expect(angleChips[0].label).toBe('90°');
  });

  it('rejected and region findings never render and never count', () => {
    const findings = [
      finding({ id: 'a' }),
      finding({ id: 'b', status: 'rejected' }),
      finding({ id: 'c', category: 'regions', type: 'title_block' }),
    ];
    expect(findingsBadgeCount(findings)).toBe(1);
    expect(groupFindings(findings)).toHaveLength(1);
  });

  it('whiteoutSectionsFor maps only the toggled categories with regions', () => {
    const findings = [
      finding({ id: 'a' }),
      finding({ id: 'b', category: 'dimensions', type: 'length', bbox: null }),
      finding({ id: 'c', category: 'dimensions', type: 'length', page: 2 }),
    ];
    expect(whiteoutSectionsFor(findings, ['dimensions'])).toEqual([
      { id: 'lens-c', page: 2, rect: { x: 10, y: 20, width: 80, height: 12 } },
    ]);
  });

  it('fillSuggestion respects the ≥0.7 purple-signal threshold', () => {
    const below = finding({ id: 'low', confidence: AI_SIGNAL_CONFIDENCE_MIN - 0.01 });
    expect(fillSuggestion([below], 'part_number')).toBeNull();
    const at = finding({ id: 'ok', confidence: AI_SIGNAL_CONFIDENCE_MIN });
    expect(fillSuggestion([at, below], 'part_number')?.id).toBe('ok');
    // An accepted finding is no longer a *suggestion* — no purple dot.
    expect(fillSuggestion([finding({ status: 'accepted' })], 'part_number')).toBeNull();
  });
});
