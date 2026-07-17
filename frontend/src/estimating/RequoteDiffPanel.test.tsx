/**
 * M4.12 — Requote Diff banner + explicit three-choice gate. The acceptance
 * angle covered here: the panel renders the deterministic diff + synthesis,
 * and NO callback fires without an explicit click (nothing auto-imports).
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import i18n from '../i18n';
import { RequoteDiffPanel } from './RequoteDiffPanel';
import type { RequoteDiffEntry, RequoteFinding } from './types';

const finding = (over: Partial<RequoteFinding>): RequoteFinding => ({
  type: 'note',
  category: 'requirements',
  role: null,
  value: null,
  normalized_value: null,
  units: null,
  tolerance: null,
  gdt: null,
  ...over,
});

const entry: RequoteDiffEntry = {
  part_id: 'p-new',
  match_type: 'exact_geometric',
  matched: {
    part_id: 'p-old',
    part_number: 'BR-100',
    revision: 'A',
    quote_id: 'q-old',
    quote_number: 'Q-2026-1000',
    component_id: 'c-old',
  },
  target_component_id: 'c-new',
  diff: {
    geometry_delta: {
      available: true,
      significant: false,
      volume: { a: 100000, b: 97700, delta_pct: -2.3 },
      bbox: {},
      features: {},
    },
    finding_diff: {
      added: [finding({ value: 'FAI REQUIRED' })],
      removed: [],
      changed: [
        {
          key: { type: 'diameter', role: 'bore_3' },
          a: finding({
            type: 'diameter',
            category: 'dimensions',
            role: 'bore_3',
            normalized_value: '12.5',
            tolerance: { upper: 0.01, lower: -0.01 },
          }),
          b: finding({
            type: 'diameter',
            category: 'dimensions',
            role: 'bore_3',
            normalized_value: '12.5',
            tolerance: { upper: 0.005, lower: -0.005 },
          }),
          changes: ['tolerance'],
        },
      ],
      material_changes: [],
    },
  },
  ai: { enabled: true, reason: 'ok' },
  synthesis: 'Geringfügige Änderung — engere Bohrungstoleranz.',
  choice: null,
  generated_at: '2026-07-17T09:00:00Z',
};

beforeAll(async () => {
  await i18n.changeLanguage('de');
});

function renderPanel() {
  const onImport = vi.fn();
  const onReview = vi.fn();
  const onStartFresh = vi.fn();
  render(
    <I18nextProvider i18n={i18n}>
      <RequoteDiffPanel
        entry={entry}
        busy={false}
        onImport={onImport}
        onReview={onReview}
        onStartFresh={onStartFresh}
      />
    </I18nextProvider>,
  );
  return { onImport, onReview, onStartFresh };
}

describe('RequoteDiffPanel', () => {
  it('shows the banner and expands to the diff + synthesis', () => {
    renderPanel();
    expect(screen.getByText(/Q-2026-1000/)).toBeInTheDocument();
    fireEvent.click(screen.getByText('Änderungen ansehen ▾'));
    expect(screen.getByTestId('requote-synthesis')).toHaveTextContent(
      'engere Bohrungstoleranz',
    );
    // Deterministic diff content renders alongside the AI paragraph.
    expect(screen.getByText(/Volumen: -2,3\s*%/)).toBeInTheDocument();
    expect(screen.getByText(/1 neu · 0 entfernt · 1 geändert/)).toBeInTheDocument();
  });

  it('fires no callback without an explicit click (the human gate)', () => {
    const { onImport, onReview, onStartFresh } = renderPanel();
    fireEvent.click(screen.getByText('Änderungen ansehen ▾'));
    expect(onImport).not.toHaveBeenCalled();
    expect(onReview).not.toHaveBeenCalled();
    expect(onStartFresh).not.toHaveBeenCalled();
  });

  it('routes each button to its own choice', () => {
    const { onImport, onReview, onStartFresh } = renderPanel();
    fireEvent.click(screen.getByText('Änderungen ansehen ▾'));
    fireEvent.click(screen.getByText('Router aus Q-2026-1000 übernehmen'));
    expect(onImport).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText('Diff im Detail prüfen'));
    expect(onReview).toHaveBeenCalledTimes(1);
    // Review expands the field-by-field list with the actual callouts.
    const findings = screen.getByTestId('requote-findings');
    expect(findings).toHaveTextContent('FAI REQUIRED');
    expect(findings).toHaveTextContent('bore_3');
    expect(findings).toHaveTextContent('+0.01 / -0.01 → +0.005 / -0.005');
    fireEvent.click(screen.getByText('Neu beginnen'));
    expect(onStartFresh).toHaveBeenCalledTimes(1);
  });
});
