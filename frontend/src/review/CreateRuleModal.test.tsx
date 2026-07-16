import { describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { CreateRuleModal, type NewRule } from './CreateRuleModal';

const PATHS = ['text', 'files', 'position_control_frames', 'length_tolerances'];

async function open(overrides: Partial<Parameters<typeof CreateRuleModal>[0]> = {}) {
  const onCreate = vi.fn<(rule: NewRule) => void>();
  const onClose = vi.fn();
  // renderWithProviders is async (it awaits the i18n language switch before the
  // first render) — without the await the DOM is still empty.
  await renderWithProviders(
    <CreateRuleModal
      documentPaths={PATHS}
      onCreate={onCreate}
      onClose={onClose}
      {...overrides}
    />,
  );
  return { onCreate, onClose };
}

describe('CreateRuleModal', () => {
  it('disables CREATE RULE until the rule is valid', async () => {
    await open();
    const commit = screen.getByRole('button', { name: 'REGEL ERSTELLEN' });
    expect((commit as HTMLButtonElement).disabled).toBe(true);

    await userEvent.type(screen.getByLabelText(/Name/), 'Enge Toleranz');
    await userEvent.type(screen.getByLabelText('Wert'), '0,13');
    // Still no resolution → still invalid.
    expect((commit as HTMLButtonElement).disabled).toBe(true);

    await userEvent.selectOptions(screen.getByLabelText('Auflösung hinzufügen'), 'NO_QUOTE');
    expect((commit as HTMLButtonElement).disabled).toBe(false);
  });

  it('emits the canonical AST — a numeric filter keeps its metric unit', async () => {
    const { onCreate } = await open();
    await userEvent.type(screen.getByLabelText(/Name/), 'Enge Toleranz');
    await userEvent.selectOptions(screen.getByLabelText('Signalpfad'), 'length_tolerances');
    await userEvent.clear(screen.getByLabelText('Feld'));
    await userEvent.type(screen.getByLabelText('Feld'), 'smallest_delta');
    await userEvent.type(screen.getByLabelText('Wert'), '0,13');
    await userEvent.selectOptions(screen.getByLabelText('Auflösung hinzufügen'), 'NO_QUOTE');

    await userEvent.click(screen.getByRole('button', { name: 'REGEL ERSTELLEN' }));

    expect(onCreate).toHaveBeenCalledTimes(1);
    const rule = onCreate.mock.calls[0][0];
    const group = (rule.signals[0] as { groups: { document_path: string; queries: unknown[] }[] })
      .groups[0];
    expect(group.document_path).toBe('length_tolerances');
    expect(group.queries[0]).toMatchObject({
      field_name: ['smallest_delta'],
      operator: 'lessThanOrEqual',
      // "0,13" is German decimal input — it must reach the AST as 0.13, not NaN.
      value: 0.13,
      filter_type: 'numeric',
      units: 'mm',
    });
    expect(rule.resolutions).toEqual([
      { type: 'NO_QUOTE', parameters: [], custom_label: null },
    ]);
  });

  it('emits a keyword filter when the value is not numeric', async () => {
    const { onCreate } = await open();
    await userEvent.type(screen.getByLabelText(/Name/), 'Entgraten');
    await userEvent.type(screen.getByLabelText('Wert'), 'entgrat');
    await userEvent.selectOptions(screen.getByLabelText('Auflösung hinzufügen'), 'ADD_OPERATION');
    await userEvent.click(screen.getByRole('button', { name: 'REGEL ERSTELLEN' }));

    const rule = onCreate.mock.calls[0][0];
    const group = (rule.signals[0] as { groups: { queries: unknown[] }[] }).groups[0];
    expect(group.queries[0]).toMatchObject({
      operator: 'includesCaseInsensitive',
      value: ['entgrat'],
      filter_type: 'string',
      units: null,
    });
  });

  it('never offers inches — the imperial default is dropped (CLAUDE.md §5)', async () => {
    await open();
    await userEvent.type(screen.getByLabelText('Wert'), '0,13');
    const units = screen.getByLabelText('Einheit');
    const options = within(units).getAllByRole('option').map((o) => o.getAttribute('value'));
    expect(options).toEqual(['mm', 'deg']);
  });

  it('pre-seeds a Selected item chip from a callout, and can clear it', async () => {
    await open({
      selectedItem: {
        label: '⌖ ⌀0,05 A B',
        document_path: 'position_control_frames',
        field_name: 'value',
        value: 0.05,
        units: 'mm',
      },
    });

    // The pill shows twice by design: the editor's "Selected item" chip and
    // the live preview's callout.
    expect(screen.getAllByText('⌖ ⌀0,05 A B')).toHaveLength(2);
    expect((screen.getByLabelText('Signalpfad') as HTMLSelectElement).value).toBe(
      'position_control_frames',
    );
    expect((screen.getByLabelText('Wert') as HTMLInputElement).value).toBe('0.05');

    await userEvent.click(screen.getByRole('button', { name: 'ENTFERNEN' }));
    expect(screen.queryByText('⌖ ⌀0,05 A B')).toBeNull();
  });

  it('previews the card the rule will produce, live', async () => {
    await open();
    const preview = screen.getByLabelText('Vorschau');
    expect(within(preview).getByText('Regelname')).toBeTruthy();

    await userEvent.type(screen.getByLabelText(/Name/), 'Enge Toleranz');
    expect(within(preview).getByText('Enge Toleranz')).toBeTruthy();

    await userEvent.selectOptions(screen.getByLabelText('Auflösung hinzufügen'), 'NO_QUOTE');
    expect(within(preview).getByText('Nicht anbieten')).toBeTruthy();
  });

  it('reveals the assignee field only once a resolution exists', async () => {
    await open();
    expect(screen.queryByLabelText('Zuständig')).toBeNull();

    await userEvent.selectOptions(screen.getByLabelText('Auflösung hinzufügen'), 'RESOLVE');

    expect(screen.getByLabelText('Zuständig')).toBeTruthy();
  });

  it('creates nothing without an explicit CREATE RULE click', async () => {
    const { onCreate } = await open();
    await userEvent.type(screen.getByLabelText(/Name/), 'Enge Toleranz');
    await userEvent.type(screen.getByLabelText('Wert'), '0,13');
    await userEvent.selectOptions(screen.getByLabelText('Auflösung hinzufügen'), 'NO_QUOTE');

    // Everything is valid — but nothing is written until the footer is clicked.
    expect(onCreate).not.toHaveBeenCalled();
  });
});
