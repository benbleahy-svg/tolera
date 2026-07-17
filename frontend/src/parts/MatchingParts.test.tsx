import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { PartMatchesChip } from './MatchingParts';
import type { PartMatches } from './api';

const getMatches = vi.fn();
const importRouter = vi.fn();

vi.mock('./api', () => ({
  usePartsApi: () => ({ getMatches, importRouter }),
}));

function matches(overrides: Partial<PartMatches> = {}): PartMatches {
  return {
    part_id: 'subject',
    subject: {
      part_number: '3601215',
      revision: 'E',
      name: 'Offset Connector',
      primary_filename: '3601215_OFFSET_CONNECTOR.STEP',
    },
    total: 3,
    buckets: [
      { key: 'exact_file', status: 'ready', count: 1, matches: [card('twin')] },
      { key: 'exact_geometric', status: 'ready', count: 0, matches: [] },
      { key: 'file_name', status: 'ready', count: 0, matches: [] },
      { key: 'part_number', status: 'ready', count: 0, matches: [] },
      { key: 'similar_geometries', status: 'processing', count: 0, matches: [] },
      {
        key: 'historical',
        status: 'ready',
        count: 1,
        matches: [
          card('hist', {
            quote_count: 1,
            quotes: [
              {
                quote_id: 'q1',
                number: 'Q-2026-0100',
                quote_item_id: 'qi1',
                component_id: 'comp-hist',
              },
            ],
          }),
        ],
      },
    ],
    ...overrides,
  };
}

function card(id: string, extra: Record<string, unknown> = {}) {
  return {
    part_id: id,
    part_number: `PN-${id}`,
    revision: null,
    name: null,
    primary_filename: `${id}.step`,
    archived: false,
    quote_count: 0,
    quotes: [],
    ...extra,
  };
}

describe('PartMatchesChip + MatchingPartsModal (M2.12)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders no chip when there are no matches', async () => {
    getMatches.mockResolvedValue(matches({ total: 0 }));
    await renderWithProviders(<PartMatchesChip partId="subject" />);
    await waitFor(() => expect(getMatches).toHaveBeenCalledWith('subject'));
    expect(screen.queryByTestId('match-chip')).not.toBeInTheDocument();
  });

  it('opens the modal with all six buckets; a processing bucket is disabled', async () => {
    getMatches.mockResolvedValue(matches());
    await renderWithProviders(<PartMatchesChip partId="subject" />);

    await userEvent.click(await screen.findByTestId('match-chip'));
    expect(screen.getByTestId('matching-parts-modal')).toBeInTheDocument();
    // Subject preview.
    expect(screen.getByText('3601215_OFFSET_CONNECTOR.STEP')).toBeInTheDocument();
    // All six buckets in the PP order, counts attached.
    expect(screen.getByTestId('bucket-exact_file')).toHaveTextContent(
      'Exakte Datei-Übereinstimmung (1)',
    );
    expect(screen.getByTestId('bucket-exact_geometric')).toHaveTextContent(
      'Exakte Geometrie-Übereinstimmung (0)',
    );
    // The similar bucket is still interrogating — chip + disabled toggle.
    expect(screen.getByTestId('bucket-similar_geometries')).toHaveTextContent(
      'Geometrie wird analysiert …',
    );
    expect(screen.getByTestId('bucket-similar_geometries')).toBeDisabled();
    expect(screen.getByTestId('bucket-historical')).toHaveTextContent('Frühere Angebote (1)');
  });

  it('expands a bucket to its match cards with quote links', async () => {
    getMatches.mockResolvedValue(matches());
    await renderWithProviders(<PartMatchesChip partId="subject" />);
    await userEvent.click(await screen.findByTestId('match-chip'));

    await userEvent.click(screen.getByTestId('bucket-historical'));
    expect(await screen.findByTestId('match-card-hist')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Q-2026-0100' })).toHaveAttribute(
      'href',
      '/quotes/q1',
    );
  });

  it('imports a historical router and reports back', async () => {
    getMatches.mockResolvedValue(matches());
    importRouter.mockResolvedValue({});
    const onImported = vi.fn();
    await renderWithProviders(
      <PartMatchesChip partId="subject" componentId="comp-target" editable onImported={onImported} />,
    );
    await userEvent.click(await screen.findByTestId('match-chip'));
    await userEvent.click(screen.getByTestId('bucket-historical'));
    await userEvent.click(await screen.findByText('Übernehmen'));

    await waitFor(() => expect(importRouter).toHaveBeenCalledWith('comp-target', 'comp-hist'));
    expect(onImported).toHaveBeenCalled();
    // The modal closes after a successful import.
    expect(screen.queryByTestId('matching-parts-modal')).not.toBeInTheDocument();
  });

  it('hides the import action when not editable', async () => {
    getMatches.mockResolvedValue(matches());
    await renderWithProviders(<PartMatchesChip partId="subject" componentId="comp-target" />);
    await userEvent.click(await screen.findByTestId('match-chip'));
    await userEvent.click(screen.getByTestId('bucket-historical'));

    expect(await screen.findByTestId('match-card-hist')).toBeInTheDocument();
    expect(screen.queryByText('Übernehmen')).not.toBeInTheDocument();
  });
});
