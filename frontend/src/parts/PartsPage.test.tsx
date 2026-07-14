import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { makeMe, renderWithProviders } from '../test/render';
import { PartsPage } from './PartsPage';
import type { Part } from './api';

const listParts = vi.fn();
const uploadLibraryParts = vi.fn();
const archivePart = vi.fn();
const restorePart = vi.fn();
const deletePart = vi.fn();
const mergeParts = vi.fn();
const listFiles = vi.fn();

// Mock the parts API module so the page never touches Clerk/network.
vi.mock('./api', () => ({
  usePartsApi: () => ({
    listParts,
    uploadLibraryParts,
    archivePart,
    restorePart,
    deletePart,
    mergeParts,
    listFiles,
  }),
  formatBytes: (n: number) => `${n} B`,
}));

function part(id: string, extra: Partial<Part> = {}): Part {
  return {
    id,
    primary_file_id: null,
    name: null,
    part_number: null,
    revision: null,
    archived: false,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    primary_filename: null,
    primary_file_type: null,
    process: null,
    ...extra,
  };
}

describe('PartsPage (Part Library, M2.12)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listParts.mockResolvedValue([]);
    listFiles.mockResolvedValue([]);
  });

  it('renders the card grid with filename, part#/rev and process', async () => {
    listParts.mockResolvedValue([
      part('p1', {
        primary_filename: 'Halter-4711.step',
        primary_file_type: 'brep_cad',
        part_number: 'HALTER-4711',
        revision: 'B',
        process: 'CNC-Fräsen',
      }),
    ]);
    await renderWithProviders(<PartsPage />);

    expect(await screen.findByText('Halter-4711.step')).toBeInTheDocument();
    expect(screen.getByText('HALTER-4711 · Rev B')).toBeInTheDocument();
    expect(screen.getByText('CNC-Fräsen')).toBeInTheDocument();
    // German-first chrome: tabs + upload.
    expect(screen.getByRole('tab', { name: 'Team-Teile' })).toBeInTheDocument();
    expect(screen.getByText('Neues Teil hochladen')).toBeInTheDocument();
  });

  it('searches via the q parameter (debounced)', async () => {
    await renderWithProviders(<PartsPage />);
    await waitFor(() => expect(listParts).toHaveBeenCalled());

    await userEvent.type(screen.getByRole('searchbox'), 'halter');
    await waitFor(() =>
      expect(listParts).toHaveBeenCalledWith({ tab: 'team', q: 'halter' }),
    );
  });

  it('switches to the Archived tab and restores a part', async () => {
    listParts.mockImplementation(({ tab }: { tab: string }) =>
      Promise.resolve(
        tab === 'archived' ? [part('p2', { name: 'Altteil', archived: true })] : [],
      ),
    );
    restorePart.mockResolvedValue(part('p2'));
    await renderWithProviders(<PartsPage />);

    await userEvent.click(screen.getByRole('tab', { name: 'Archiviert' }));
    expect(await screen.findByText('Altteil')).toBeInTheDocument();
    await userEvent.click(screen.getByText('Wiederherstellen'));
    expect(restorePart).toHaveBeenCalledWith('p2');
  });

  it('deletes an archived part only after the two-step confirm', async () => {
    listParts.mockImplementation(({ tab }: { tab: string }) =>
      Promise.resolve(tab === 'archived' ? [part('p3', { name: 'Weg damit' })] : []),
    );
    deletePart.mockResolvedValue(undefined);
    await renderWithProviders(<PartsPage />);

    await userEvent.click(screen.getByRole('tab', { name: 'Archiviert' }));
    await userEvent.click(await screen.findByText('Löschen'));
    expect(deletePart).not.toHaveBeenCalled(); // first click only arms the confirm
    await userEvent.click(screen.getByText('Endgültig löschen?'));
    expect(deletePart).toHaveBeenCalledWith('p3');
  });

  it('merges selected parts with a chosen primary (CAD preselected)', async () => {
    listParts.mockResolvedValue([
      part('cad', { primary_filename: '5-X-9.step', primary_file_type: 'brep_cad' }),
      part('pdf', { primary_filename: '5-X-9__B.pdf', primary_file_type: 'document' }),
    ]);
    mergeParts.mockResolvedValue(part('cad'));
    await renderWithProviders(<PartsPage />);

    await screen.findByText('5-X-9.step');
    await userEvent.click(screen.getByText('Teile auswählen'));
    for (const box of screen.getAllByRole('checkbox')) await userEvent.click(box);
    await userEvent.click(screen.getByText('Als ergänzende Dateien zusammenführen'));

    // The CAD part is the preselected primary (KB: choose a model if you have one).
    const dialog = await screen.findByTestId('merge-dialog');
    expect(dialog).toBeInTheDocument();
    const radios = screen.getAllByRole('radio');
    expect((radios[0] as HTMLInputElement).checked).toBe(true);
    await userEvent.click(screen.getByText('Zusammenführen'));
    expect(mergeParts).toHaveBeenCalledWith(['cad', 'pdf'], 'cad');
  });

  it('shows the shared-with-me empty state (M6)', async () => {
    await renderWithProviders(<PartsPage />);
    await userEvent.click(screen.getByRole('tab', { name: 'Für mich freigegeben' }));
    expect(
      screen.getByText('Externe Freigaben folgen mit der Lieferanten-Kollaboration.'),
    ).toBeInTheDocument();
  });

  it('hides write chrome without quote_edit', async () => {
    listParts.mockResolvedValue([part('p1', { name: 'Nur lesen' })]);
    await renderWithProviders(<PartsPage />, {
      me: makeMe({ effective_permissions: ['view_all'], roles: ['viewer'] }),
    });

    expect(await screen.findByText('Nur lesen')).toBeInTheDocument();
    expect(screen.queryByText('Neues Teil hochladen')).not.toBeInTheDocument();
    expect(screen.queryByText('Teile auswählen')).not.toBeInTheDocument();
  });
});
