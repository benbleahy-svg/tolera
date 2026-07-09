/**
 * Configure → Custom Tables (M1.9): create a typed table, open it, edit a
 * typed cell (numeric parse, boolean select), save rows, import a CSV.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { CustomTablesPage } from './CustomTablesPage';
import type { CustomTableDetail, CustomTableOut } from './api';

const listTables = vi.fn();
const getTable = vi.fn();
const createTable = vi.fn();
const renameTable = vi.fn();
const deleteTable = vi.fn();
const replaceRows = vi.fn();
const importCsv = vi.fn();

vi.mock('./api', () => ({
  useConfigureApi: () => ({
    listTables,
    getTable,
    createTable,
    renameTable,
    deleteTable,
    replaceRows,
    importCsv,
  }),
}));

const TABLE: CustomTableOut = {
  id: 't1',
  name: 'materialpreise',
  columns: [
    { name: 'material', type: 'string' },
    { name: 'preis', type: 'numeric' },
    { name: 'schwierig', type: 'boolean' },
  ],
  row_count: 1,
};

const DETAIL: CustomTableDetail = {
  ...TABLE,
  rows: [{ row_number: 1, material: 'Titan', preis: 80, schwierig: true }],
};

beforeEach(() => {
  vi.clearAllMocks();
  listTables.mockResolvedValue([TABLE]);
  getTable.mockResolvedValue(DETAIL);
  replaceRows.mockResolvedValue(DETAIL);
  importCsv.mockResolvedValue(TABLE);
});

describe('CustomTablesPage', () => {
  it('lists tables and opens one into the grid', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CustomTablesPage />);
    await user.click(await screen.findByRole('button', { name: /materialpreise/ }));
    expect(await screen.findByDisplayValue('Titan')).toBeInTheDocument();
    expect(screen.getByDisplayValue('80')).toBeInTheDocument();
  });

  it('creates a table with typed columns', async () => {
    const user = userEvent.setup();
    createTable.mockResolvedValue({ ...TABLE, id: 't2', name: 'zuschnitt', row_count: 0 });
    getTable.mockResolvedValue({ ...DETAIL, id: 't2', name: 'zuschnitt', rows: [] });
    renderWithProviders(<CustomTablesPage />);
    await user.type(await screen.findByLabelText('Tabellenname'), 'zuschnitt');
    await user.type(screen.getByLabelText('Spaltenname'), 'laenge');
    await user.selectOptions(screen.getByLabelText('Spaltentyp'), 'numeric');
    await user.click(screen.getByRole('button', { name: 'Tabelle anlegen' }));
    await waitFor(() =>
      expect(createTable).toHaveBeenCalledWith('zuschnitt', [{ name: 'laenge', type: 'numeric' }]),
    );
  });

  it('edits typed cells and saves all rows', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CustomTablesPage />);
    await user.click(await screen.findByRole('button', { name: /materialpreise/ }));
    const price = await screen.findByDisplayValue('80');
    await user.clear(price);
    await user.type(price, '90,5'); // German decimal comma parses to a number
    await user.click(screen.getByRole('button', { name: 'Zeilen speichern' }));
    await waitFor(() =>
      expect(replaceRows).toHaveBeenCalledWith('t1', [
        { material: 'Titan', preis: 90.5, schwierig: true },
      ]),
    );
  });

  it('imports a CSV file', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CustomTablesPage />);
    await user.click(await screen.findByRole('button', { name: /materialpreise/ }));
    await screen.findByDisplayValue('Titan');
    const file = new File(['material,preis,schwierig\nStahl,4,\n'], 'preise.csv', {
      type: 'text/csv',
    });
    await user.upload(screen.getByLabelText('CSV importieren', { selector: 'input' }), file);
    await waitFor(() => expect(importCsv).toHaveBeenCalledWith('t1', file));
  });
});
