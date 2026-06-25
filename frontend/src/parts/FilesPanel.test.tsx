import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { makeMe, renderWithProviders } from '../test/render';
import { FilesPanel } from './FilesPanel';

const listFiles = vi.fn();
const uploadFiles = vi.fn();
const setPrimary = vi.fn();
const deleteFile = vi.fn();
const downloadFile = vi.fn();

// Mock the parts API module so the panel never touches Clerk/network.
vi.mock('./api', () => ({
  usePartsApi: () => ({ listFiles, uploadFiles, setPrimary, deleteFile, downloadFile }),
  formatBytes: (n: number) => `${n} B`,
}));

function file(name: string, role: 'primary' | 'supporting', extra: Record<string, unknown> = {}) {
  return {
    id: `f-${name}`,
    part_id: 'p1',
    filename: name,
    file_type: 'brep_cad',
    content_type: 'application/step',
    size_bytes: 100,
    role,
    is_redacted: false,
    created_at: '2026-06-25T00:00:00Z',
    ...extra,
  };
}

describe('FilesPanel', () => {
  beforeEach(() => {
    listFiles.mockReset();
    uploadFiles.mockReset();
    setPrimary.mockReset();
    deleteFile.mockReset();
    downloadFile.mockReset();
  });

  it('lists a part’s files with the PRIMARY tagged', async () => {
    listFiles.mockResolvedValue([
      file('bracket.step', 'primary'),
      file('drawing.pdf', 'supporting', { file_type: 'document' }),
    ]);
    await renderWithProviders(<FilesPanel partId="p1" />);

    expect(await screen.findByText('bracket.step')).toBeInTheDocument();
    expect(screen.getByText('drawing.pdf')).toBeInTheDocument();
    expect(screen.getByText('PRIMÄR')).toBeInTheDocument(); // de default locale
  });

  it('shows write actions for an editor and downloads on click', async () => {
    listFiles.mockResolvedValue([file('bracket.step', 'primary')]);
    await renderWithProviders(<FilesPanel partId="p1" />); // default makeMe = estimator (quote_edit)

    expect(await screen.findByText('Dateien hochladen')).toBeInTheDocument();
    await userEvent.click(screen.getByText('Herunterladen'));
    expect(downloadFile).toHaveBeenCalledWith('p1', 'f-bracket.step', 'bracket.step');
  });

  it('lets an editor make a supporting file primary', async () => {
    listFiles.mockResolvedValue([
      file('bracket.step', 'primary'),
      file('drawing.pdf', 'supporting', { file_type: 'document' }),
    ]);
    setPrimary.mockResolvedValue(file('drawing.pdf', 'primary'));
    await renderWithProviders(<FilesPanel partId="p1" />);

    await screen.findByText('Als Primär festlegen');
    const before = listFiles.mock.calls.length;
    await userEvent.click(screen.getByText('Als Primär festlegen'));
    expect(setPrimary).toHaveBeenCalledWith('p1', 'f-drawing.pdf');
    // The panel reloads its list after a successful swap.
    await waitFor(() => expect(listFiles.mock.calls.length).toBeGreaterThan(before));
  });

  it('hides write actions without quote_edit', async () => {
    listFiles.mockResolvedValue([file('bracket.step', 'primary')]);
    await renderWithProviders(<FilesPanel partId="p1" />, {
      me: makeMe({ effective_permissions: ['view_all'], roles: ['viewer'] }),
    });

    expect(await screen.findByText('Herunterladen')).toBeInTheDocument(); // read OK
    expect(screen.queryByText('Dateien hochladen')).not.toBeInTheDocument();
    expect(screen.queryByText('Löschen')).not.toBeInTheDocument();
  });
});
