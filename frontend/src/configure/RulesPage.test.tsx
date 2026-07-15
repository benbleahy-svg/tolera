/**
 * Configure → Rules (M3.6, spec #rules-schema): the rules config page — list
 * the org's review rules and import/export the whole set as ONE JSON string
 * (paste-in). The Create Rule modal is M3.8; this page owns only the portable
 * serialized form.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { RulesPage } from './RulesPage';
import type { RuleOut } from './api';

const listRules = vi.fn();
const exportRules = vi.fn();
const importRules = vi.fn();

// A stable hook return (like the real useMemo'd hook) so the page's load
// effect runs once per mount, keeping call counts deterministic.
const apiMock = { listRules, exportRules, importRules };
vi.mock('./api', () => ({
  useConfigureApi: () => apiMock,
}));

const RULES: RuleOut[] = [
  {
    id: 'row-1',
    uuid: '00000000-0000-4000-8000-000000000001',
    name: 'All tight dimension tolerances',
    description: 'Any tolerance tighter than 0.13 mm.',
    logical_operator: 'OR',
    signals: [
      {
        logical_operator: 'AND',
        groups: [
          {
            document_path: 'length_tolerances',
            logical_operator: 'AND',
            queries: [
              {
                field_name: ['smallest_delta'],
                operator: 'lessThanOrEqual',
                value: 0.13,
                value_type: 'distance',
                filter_type: 'numeric',
                units: 'mm',
              },
            ],
            count_query: null,
          },
        ],
      },
    ],
    resolutions: [
      { type: 'NO_QUOTE', parameters: [], custom_label: null },
      { type: 'RESOLVE', parameters: [], custom_label: 'Outsource' },
    ],
    default_assignee_id: null,
    is_active: true,
  },
];

const EXPORTED = '[{"name":"All tight dimension tolerances"}]';

beforeEach(() => {
  vi.clearAllMocks();
  listRules.mockResolvedValue(RULES);
  exportRules.mockResolvedValue({ rules_json: EXPORTED, count: 1 });
  importRules.mockResolvedValue({ created: 9, updated: 0 });
});

describe('RulesPage', () => {
  it('lists the org rules with signal/resolution counts', async () => {
    renderWithProviders(<RulesPage />);
    expect(await screen.findByText('All tight dimension tolerances')).toBeInTheDocument();
    const row = screen.getByText('All tight dimension tolerances').closest('tr')!;
    expect(row).toHaveTextContent('OR');
    expect(row).toHaveTextContent('1'); // one signal
    expect(row).toHaveTextContent('2'); // two resolutions
  });

  it('shows the exported canonical JSON string for copy-out', async () => {
    renderWithProviders(<RulesPage />);
    const exportBox = (await screen.findByLabelText(/Export/)) as HTMLTextAreaElement;
    await waitFor(() => expect(exportBox.value).toBe(EXPORTED));
    expect(exportBox).toHaveAttribute('readonly');
  });

  it('imports a pasted rule set and reports created/updated', async () => {
    renderWithProviders(<RulesPage />);
    await screen.findByText('All tight dimension tolerances');
    const importBox = screen.getByLabelText(/Import/);
    await userEvent.click(importBox);
    await userEvent.paste('[{"uuid":"…"}]');
    await userEvent.click(screen.getByRole('button', { name: 'Importieren' }));
    await waitFor(() => expect(importRules).toHaveBeenCalledWith('[{"uuid":"…"}]'));
    // created/updated summary is announced and the list + export refresh
    expect(await screen.findByText(/9/)).toBeInTheDocument();
    expect(listRules).toHaveBeenCalledTimes(2);
    expect(exportRules).toHaveBeenCalledTimes(2);
  });

  it('surfaces an import rejection as an error message', async () => {
    const { ApiError } = await import('../api/client');
    importRules.mockRejectedValue(
      new ApiError(422, 'invalid_rules_json', 'The pasted rules JSON does not match.'),
    );
    renderWithProviders(<RulesPage />);
    await screen.findByText('All tight dimension tolerances');
    await userEvent.click(screen.getByLabelText(/Import/));
    await userEvent.paste('nope {');
    await userEvent.click(screen.getByRole('button', { name: 'Importieren' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/does not match/);
  });
});
