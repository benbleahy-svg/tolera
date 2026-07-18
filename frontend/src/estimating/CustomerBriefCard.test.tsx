import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/render';
import { CustomerBriefCard } from './CustomerBriefCard';

const getCustomerBrief = vi.fn();

vi.mock('../quotes/api', () => ({
  useQuotesApi: () => ({ getCustomerBrief }),
}));

function brief(bullets: string[]) {
  return {
    brief: {
      version: 1,
      prompt_version: 'brief-v1',
      generated_at: '2026-07-18T09:00:00Z',
      account_name: 'Arch Medial Solutions',
      bullets,
      signals: {},
    },
    reason: 'ok',
  };
}

describe('CustomerBriefCard (M5.10)', () => {
  beforeEach(() => getCustomerBrief.mockReset());
  afterEach(() => vi.clearAllMocks());

  it('renders the About-account card with bullets when the brief is returned', async () => {
    getCustomerBrief.mockResolvedValue(
      brief(['Dieses Angebot ist mit 31.000 € ihr größtes.', 'Akzeptiert nie ohne Revision.']),
    );
    await renderWithProviders(<CustomerBriefCard quoteId="q1" />);

    expect(await screen.findByTestId('customer-brief-card')).toBeInTheDocument();
    expect(screen.getByText(/Arch Medial Solutions/)).toBeInTheDocument();
    expect(screen.getByText(/ihr größtes/)).toBeInTheDocument();
    expect(screen.getByText(/nie ohne Revision/)).toBeInTheDocument();
    expect(getCustomerBrief).toHaveBeenCalledWith('q1');
  });

  it('renders nothing when the brief is omitted (graceful — no empty state)', async () => {
    getCustomerBrief.mockResolvedValue({ brief: null, reason: 'insufficient_data' });
    const { container } = await renderWithProviders(<CustomerBriefCard quoteId="q2" />);
    await waitFor(() => expect(getCustomerBrief).toHaveBeenCalled());
    expect(screen.queryByTestId('customer-brief-card')).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  // The error path (model failure → reason "error:*", brief null) hits the same
  // "no card" render branch as the omission test above; the error→null mapping is
  // asserted server-side (test_generate_omits_on_model_error). The composer is
  // therefore never blocked by a brief failure.

  it('can be dismissed for the session', async () => {
    getCustomerBrief.mockResolvedValue(brief(['Ein Stichpunkt.']));
    await renderWithProviders(<CustomerBriefCard quoteId="q4" />);
    expect(await screen.findByTestId('customer-brief-card')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /ausblenden|dismiss/i }));
    expect(screen.queryByTestId('customer-brief-card')).not.toBeInTheDocument();
  });
});
