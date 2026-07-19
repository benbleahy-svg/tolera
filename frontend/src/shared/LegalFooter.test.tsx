/**
 * LegalFooter (M6.9) — DACH-DELTA §5 requires Impressum + Datenschutzerklärung on
 * every customer- and vendor-facing surface.
 *
 * The assertions that matter are the negative ones: the component must render
 * only what the shop actually configured, never a placeholder heading and never
 * a guessed URL.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { LegalFooter, type LegalBlock } from './LegalFooter';

const FULL: LegalBlock = {
  heading: 'Impressum',
  impressum: [
    { label: null, value: 'Fechner Zerspanung GmbH' },
    { label: null, value: 'Musterstr. 1\n80331 München' },
    { label: 'Handelsregister', value: 'Amtsgericht München, HRB 123456' },
    { label: 'USt-IdNr.', value: 'DE123456789' },
  ],
  privacy_policy_url: 'https://fechner.example/datenschutz',
};

describe('LegalFooter', () => {
  it('renders the configured Impressum lines with their de-DE labels', () => {
    render(<LegalFooter legal={FULL} />);
    expect(screen.getByText('Impressum')).toBeInTheDocument();
    expect(screen.getByText('Fechner Zerspanung GmbH')).toBeInTheDocument();
    expect(screen.getByText('Handelsregister: Amtsgericht München, HRB 123456')).toBeInTheDocument();
    expect(screen.getByText('USt-IdNr.: DE123456789')).toBeInTheDocument();
  });

  it('links the Datenschutzerklärung safely', () => {
    render(<LegalFooter legal={FULL} />);
    const link = screen.getByRole('link', { name: 'Datenschutzerklärung' });
    expect(link).toHaveAttribute('href', 'https://fechner.example/datenschutz');
    // An external link out of an unauthenticated token page must not leak the opener.
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('shows no privacy link when the shop has published no policy', () => {
    render(<LegalFooter legal={{ ...FULL, privacy_policy_url: null }} />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    // The Impressum still renders — the two parts are independent.
    expect(screen.getByText('Fechner Zerspanung GmbH')).toBeInTheDocument();
  });

  it('renders nothing at all when the org has configured neither', () => {
    // An empty "Impressum" heading reads as a legal disclosure missing its
    // content — worse than no heading.
    const { container } = render(
      <LegalFooter legal={{ heading: 'Impressum', impressum: [], privacy_policy_url: null }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the payload carries no legal block at all', () => {
    const { container } = render(<LegalFooter legal={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
