/**
 * Vendor-RFQ portal page (M6.2): the public response form. Covers the acceptance
 * criteria that are UI-side — the batch's parts render, a partial ("cannot quote")
 * response submits, the form stays open and submittable past the need-by date, and
 * prices reach the wire as exact strings. The api module is mocked wholesale (the
 * page is unauthenticated; there is no session to fake).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import i18n from '../i18n';
import { VendorRfqPage } from './VendorRfqPage';
import { fetchVendorRfq, submitVendorResponse, vendorFileUrl, vendorPdfUrl } from './api';
import type { VendorRfq } from './types';

vi.mock('./api');

const mockFetch = vi.mocked(fetchVendorRfq);
const mockSubmit = vi.mocked(submitVendorResponse);

function rfq(overrides: Partial<VendorRfq> = {}): VendorRfq {
  return {
    rfq_number: 'RFQ-1001',
    need_by_date: '2026-09-01',
    is_past_due: false,
    message: 'Bitte um Angebot für Eloxieren.',
    shop: { name: 'Fechner GmbH', slug: 'fechner', country: 'DE', locale: 'de-DE' },
    vendor: { name: 'Eloxal Schmidt GmbH' },
    lines: [
      {
        id: 'line-1',
        part_number: 'PN-1000',
        revision: 'B',
        description: 'Halterung',
        process: 'Eloxieren',
        quantities: [1, 10],
        estimator_notes: 'Schichtdicke 20 µm',
        files: [{ id: 'file-1', filename: 'zeichnung.pdf', size_bytes: 1234 }],
      },
      {
        id: 'line-2',
        part_number: 'PN-2000',
        revision: null,
        description: 'Deckel',
        process: 'Eloxieren',
        quantities: [5],
        estimator_notes: null,
        files: [],
      },
    ],
    response: null,
    ...overrides,
  };
}

function renderPage() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={['/vendor-rfq/tok-123']}>
        <Routes>
          <Route path="/vendor-rfq/:token" element={<VendorRfqPage />} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  );
}

describe('VendorRfqPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockSubmit.mockResolvedValue({ submitted_at: '2026-08-01T10:00:00+00:00', is_late: false });
    // The URL builders are pure — keep their real shape so the rendered hrefs are
    // the ones the server actually serves.
    vi.mocked(vendorFileUrl).mockImplementation(
      (token, fileId) => `/api/public/vendor-rfq/${token}/files/${fileId}`,
    );
    vi.mocked(vendorPdfUrl).mockImplementation((token) => `/api/public/vendor-rfq/${token}/pdf`);
  });

  it('renders the batch parts, the vendor identity and the granted file link', async () => {
    mockFetch.mockResolvedValue(rfq());
    renderPage();

    expect(await screen.findByText('Fechner GmbH')).toBeInTheDocument();
    expect(screen.getByText(/Eloxal Schmidt GmbH/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /PN-1000/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /PN-2000/ })).toBeInTheDocument();
    expect(screen.getByText('Schichtdicke 20 µm')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'zeichnung.pdf' })).toHaveAttribute(
      'href',
      '/api/public/vendor-rfq/tok-123/files/file-1',
    );
  });

  it('posts prices as exact strings, one row per requested quantity', async () => {
    mockFetch.mockResolvedValue(rfq());
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { name: /PN-1000/ });

    await user.type(screen.getByLabelText(/Stückpreis für 10 Stück, Teil PN-1000/), '12.5000');
    await user.click(screen.getByRole('button', { name: /Angebot absenden/ }));

    expect(mockSubmit).toHaveBeenCalledTimes(1);
    const [token, request] = mockSubmit.mock.calls[0];
    expect(token).toBe('tok-123');
    const line1 = request.lines.find((l) => l.rfq_line_id === 'line-1')!;
    // Exact string on the wire — never a rounded JS number.
    expect(line1.prices).toEqual([
      { quantity: 10, unit_price: '12.5000', lead_time_days: null },
    ]);
    // An untouched quantity is simply not sent (no invented zero price).
    expect(line1.prices.some((p) => p.quantity === 1)).toBe(false);
  });

  it('submits a partial response and sends no prices for a cannot-quote line', async () => {
    mockFetch.mockResolvedValue(rfq());
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { name: /PN-1000/ });

    await user.type(screen.getByLabelText(/Stückpreis für 10 Stück, Teil PN-1000/), '12.5000');
    const cannotQuote = screen.getAllByRole('checkbox', { name: /nicht anbieten/ })[1];
    await user.click(cannotQuote);
    await user.click(screen.getByRole('button', { name: /Angebot absenden/ }));

    const [, request] = mockSubmit.mock.calls[0];
    const line2 = request.lines.find((l) => l.rfq_line_id === 'line-2')!;
    expect(line2.cannot_quote).toBe(true);
    expect(line2.prices).toEqual([]);
  });

  it('stays open and submittable past the need-by date (soft cutoff)', async () => {
    mockFetch.mockResolvedValue(rfq({ is_past_due: true }));
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { name: /PN-1000/ });

    // Informational note, never a closed state.
    expect(screen.getByText(/weiterhin einreichen/)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Stückpreis für 10 Stück, Teil PN-1000/), '9.0000');
    const submit = screen.getByRole('button', { name: /Angebot absenden/ });
    expect(submit).toBeEnabled();
    await user.click(submit);
    expect(mockSubmit).toHaveBeenCalledTimes(1);
  });

  it('reopens pre-filled from a prior submission so a correction is an edit', async () => {
    mockFetch.mockResolvedValue(
      rfq({
        response: {
          currency: 'CHF',
          valid_until: '2026-10-31',
          notes: 'Ab Werk.',
          is_late: false,
          submitted_at: '2026-08-01T10:00:00+00:00',
          attachment_filename: null,
          lines: [
            {
              rfq_line_id: 'line-1',
              cannot_quote: false,
              notes: null,
              prices: [{ quantity: 10, unit_price: '11.0000', lead_time_days: 7 }],
            },
          ],
        },
      }),
    );
    renderPage();
    await screen.findByRole('heading', { name: /PN-1000/ });

    expect(screen.getByLabelText(/Stückpreis für 10 Stück, Teil PN-1000/)).toHaveValue('11.0000');
    expect(screen.getByLabelText(/Lieferzeit für 10 Stück, Teil PN-1000/)).toHaveValue(7);
  });

  it('shows an invalid-link state when the token is rejected', async () => {
    mockFetch.mockRejectedValue(new Error('401'));
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent(/ungültig/);
  });
});
