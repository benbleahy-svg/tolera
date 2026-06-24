/**
 * Proves the BRAND config propagates: with a different brand mocked in, the
 * wordmark renders the configured name (and no hardcoded "Tolera"), so a
 * rename/white-label is config-only — zero code edits (AC).
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('../brand', () => ({
  BRAND: {
    name: 'Werkbank Pro',
    shortName: 'W',
    domains: { marketing: 'werkbank.example', app: 'app.werkbank.example', rfq: 'rfq.werkbank.example' },
    logoUrl: null,
    primaryColor: '',
  },
}));

import { BrandMark } from './BrandMark';

describe('BRAND propagation', () => {
  it('renders the configured product name, not a hardcoded one', () => {
    render(<BrandMark collapsed={false} />);
    expect(screen.getByText('Werkbank Pro')).toBeInTheDocument();
    expect(screen.queryByText('Tolera')).not.toBeInTheDocument();
  });

  it('collapses to the short glyph without the full name', () => {
    render(<BrandMark collapsed={true} />);
    expect(screen.getByText('W')).toBeInTheDocument();
    expect(screen.queryByText('Werkbank Pro')).not.toBeInTheDocument();
  });
});
