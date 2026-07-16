import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { SuggestedActionsStrip } from './SuggestedActionsStrip';

const listSuggestedActions = vi.fn();
const dismissSuggestedAction = vi.fn();
const importRules = vi.fn();

// Stable object per the real hook's useMemo — a fresh object each render would
// re-run the load effect in a loop (its dep is the api instance).
const ruleSuggestApi = {
  listSuggestedActions,
  dismissSuggestedAction,
  getRuleSuggestion: vi.fn(),
};
const configureApi = { importRules };

vi.mock('../review/api', async () => {
  const actual = await vi.importActual<typeof import('../review/api')>('../review/api');
  return { ...actual, useRuleSuggestApi: () => ruleSuggestApi };
});

vi.mock('../configure/api', () => ({ useConfigureApi: () => configureApi }));

function suggestion(overrides: Record<string, unknown> = {}) {
  return {
    id: 'sa1',
    kind: 'rule_suggestion',
    status: 'open',
    operation_def_id: 'op-1',
    created_at: '2026-07-16T09:00:00Z',
    payload: {
      version: 1,
      sentence: '„Entgraten“ wurde 3× manuell hinzugefügt. Als Regel automatisieren?',
      pattern: {
        operation_def_id: 'op-1',
        operation_name: 'Entgraten',
        process_family: 'MILLING',
        material_class_id: 'mc-1',
        material_class: 'Edelstahl',
        part_count: 3,
      },
      rule_draft: {
        name: 'Entgraten für Fräs-Teile aus Edelstahl',
        description: 'auto',
        operation_def_id: 'op-1',
        operation_name: 'Entgraten',
        process_family: 'MILLING',
        material_class: 'Edelstahl',
        keyword: 'Edelstahl',
      },
    },
    ...overrides,
  };
}

describe('SuggestedActionsStrip', () => {
  it('renders an open suggestion and opens the Create Rule dialog pre-seeded', async () => {
    listSuggestedActions.mockResolvedValue([suggestion()]);
    await renderWithProviders(<SuggestedActionsStrip />);

    expect(await screen.findByTestId('rule-suggestion')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Regel erstellen' }));

    // Dialog is pre-seeded with the detected pattern (name + keyword condition).
    const nameField = await screen.findByDisplayValue('Entgraten für Fräs-Teile aus Edelstahl');
    expect(nameField).toBeInTheDocument();
    expect(screen.getByDisplayValue('Edelstahl')).toBeInTheDocument();
  });

  it('creates NO rule until the human clicks CREATE RULE (human gate)', async () => {
    listSuggestedActions.mockResolvedValue([suggestion()]);
    importRules.mockResolvedValue({ created: 1, updated: 0 });
    dismissSuggestedAction.mockResolvedValue({});
    await renderWithProviders(<SuggestedActionsStrip />);

    await userEvent.click(await screen.findByRole('button', { name: 'Regel erstellen' }));
    // Opening the dialog authored nothing.
    expect(importRules).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: 'REGEL ERSTELLEN' }));
    await waitFor(() => expect(importRules).toHaveBeenCalledTimes(1));
    // The suggestion is consumed once the rule is authored.
    expect(dismissSuggestedAction).toHaveBeenCalledWith('sa1');
  });

  it('dismiss removes the chip', async () => {
    listSuggestedActions.mockResolvedValue([suggestion()]);
    dismissSuggestedAction.mockResolvedValue({});
    await renderWithProviders(<SuggestedActionsStrip />);

    await screen.findByTestId('rule-suggestion');
    await userEvent.click(screen.getByRole('button', { name: 'Ablehnen' }));
    await waitFor(() => expect(screen.queryByTestId('rule-suggestion')).not.toBeInTheDocument());
    expect(dismissSuggestedAction).toHaveBeenCalledWith('sa1');
  });
});
