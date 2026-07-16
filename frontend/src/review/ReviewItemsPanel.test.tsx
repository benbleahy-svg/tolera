import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { ReviewItemsPanel } from './ReviewItemsPanel';
import type { ReviewItemOut } from './api';

const listForComponent = vi.fn();
const resolve = vi.fn();
const assign = vi.fn();
const priorDecisions = vi.fn();

// A stable object: the panel's load effect depends on the api identity, so a
// fresh object each render would loop.
const apiMock = {
  listForComponent,
  listForQuote: vi.fn(),
  generate: vi.fn(),
  resolve,
  assign,
  setAll: vi.fn(),
  priorDecisions,
  listMessages: vi.fn(),
  postMessage: vi.fn(),
};
vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return { ...actual, useReviewApi: () => apiMock };
});

const COMPONENT_ID = '11111111-1111-4111-8111-111111111111';

function item(overrides: Partial<ReviewItemOut> = {}): ReviewItemOut {
  return {
    id: 'item-1',
    rule_id: 'rule-1',
    rule_name: 'Fehlende Zeichnung',
    component_id: COMPONENT_ID,
    quote_id: 'q1',
    quote_item_id: 'qi1',
    status: 'open',
    assignee_id: null,
    resolution_type: null,
    resolution_label: null,
    resolved_at: null,
    resolved_by: null,
    detail: { matched_text: 'Alle Kanten entgraten' },
    resolution_options: [
      { type: 'RESOLVE', parameters: [], custom_label: 'Kunde kontaktiert' },
      { type: 'NO_QUOTE', parameters: [], custom_label: null },
    ],
    ...overrides,
  };
}

describe('ReviewItemsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listForComponent.mockResolvedValue([item()]);
    priorDecisions.mockResolvedValue([]);
  });

  it('renders a card with its rule name, matched callout and the rule’s own actions', async () => {
    renderWithProviders(<ReviewItemsPanel componentId={COMPONENT_ID} />);

    const card = await screen.findByTestId('review-card');
    expect(within(card).getByText('Fehlende Zeichnung')).toBeTruthy();
    expect(within(card).getByText('Alle Kanten entgraten')).toBeTruthy();
    // The buttons are the rule's configured resolutions — not a fixed list.
    expect(within(card).getByText('Kunde kontaktiert')).toBeTruthy();
    expect(within(card).getByText('Nicht anbieten')).toBeTruthy();
  });

  it('resolves via the clicked option and reflects the resolution', async () => {
    resolve.mockResolvedValue(
      item({ status: 'resolved', resolution_type: 'RESOLVE', resolution_label: 'Kunde kontaktiert' }),
    );
    renderWithProviders(<ReviewItemsPanel componentId={COMPONENT_ID} />);

    await userEvent.click(await screen.findByText('Kunde kontaktiert'));

    expect(resolve).toHaveBeenCalledWith('item-1', 'RESOLVE', 'Kunde kontaktiert');
    // Unresolved-only is the default filter, so a resolved item leaves the list.
    await waitFor(() => expect(screen.queryByTestId('review-card')).toBeNull());
  });

  it('surfaces the unresolved count — the panel is a burn-down list', async () => {
    listForComponent.mockResolvedValue([item(), item({ id: 'item-2' })]);
    renderWithProviders(<ReviewItemsPanel componentId={COMPONENT_ID} />);

    await waitFor(() =>
      expect(screen.getByTestId('review-unresolved-count').textContent).toContain('2'),
    );
  });

  it('shows resolved items only when the Unresolved filter is off', async () => {
    listForComponent.mockResolvedValue([
      item({ id: 'done', status: 'resolved', resolution_type: 'RESOLVE', resolution_label: 'Erledigt' }),
    ]);
    renderWithProviders(<ReviewItemsPanel componentId={COMPONENT_ID} />);

    await waitFor(() => expect(screen.queryByTestId('review-card')).toBeNull());

    await userEvent.click(screen.getByLabelText('Nur offene'));
    expect(await screen.findByTestId('review-card')).toBeTruthy();
  });

  it('tells the caller when an item resolves, so the router can refetch', async () => {
    const onResolved = vi.fn();
    resolve.mockResolvedValue(item({ status: 'resolved', resolution_type: 'NO_QUOTE' }));
    renderWithProviders(<ReviewItemsPanel componentId={COMPONENT_ID} onResolved={onResolved} />);

    await userEvent.click(await screen.findByText('Nicht anbieten'));

    await waitFor(() => expect(onResolved).toHaveBeenCalled());
  });

  it('reports a failed resolve instead of pretending it worked', async () => {
    resolve.mockRejectedValue(new Error('409'));
    renderWithProviders(<ReviewItemsPanel componentId={COMPONENT_ID} />);

    await userEvent.click(await screen.findByText('Kunde kontaktiert'));

    expect((await screen.findByRole('alert')).textContent).toBeTruthy();
    expect(screen.getByTestId('review-card')).toBeTruthy();
  });

  it('fetches prior decisions on demand (§6.4), not on load', async () => {
    priorDecisions.mockResolvedValue([
      { id: 'p1', component_id: 'c2', resolution_type: 'RESOLVE', resolution_label: 'Fremdvergabe', resolved_at: null, resolved_by: null },
    ]);
    renderWithProviders(<ReviewItemsPanel componentId={COMPONENT_ID} />);
    await screen.findByTestId('review-card');
    expect(priorDecisions).not.toHaveBeenCalled();

    await userEvent.click(screen.getByText('Frühere Entscheidungen'));

    expect(await screen.findByText('Fremdvergabe')).toBeTruthy();
  });
});
