/**
 * M4.12 — Requote Diff banner + explicit three-choice gate. The acceptance
 * angle covered here: the panel renders the deterministic diff + synthesis,
 * and NO callback fires without an explicit click (nothing auto-imports).
 *
 * M4.13 — the shared-panel assembly offer: banner only when the server offers
 * it, Accept All only when the server says eligible (suppressed note
 * otherwise), the 60-second undo chip after an Accept-All import — and again,
 * no callback without an explicit click.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import i18n from '../i18n';
import { RequoteDiffPanel } from './RequoteDiffPanel';
import type { AssemblyState, RequoteDiffEntry, RequoteFinding } from './types';

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

const offeredState: AssemblyState = {
  offered: true,
  accept_all_eligible: true,
  blockers: [],
  quote_count: 3,
  undo_ttl_seconds: 60,
};

beforeAll(async () => {
  await i18n.changeLanguage('de');
});

function renderPanel(over: Partial<RequoteDiffEntry> = {}) {
  const onImport = vi.fn();
  const onReview = vi.fn();
  const onStartFresh = vi.fn();
  const onAcceptAll = vi.fn();
  const onImportForReview = vi.fn();
  const onUndo = vi.fn();
  render(
    <I18nextProvider i18n={i18n}>
      <RequoteDiffPanel
        entry={{ ...entry, ...over }}
        busy={false}
        onImport={onImport}
        onReview={onReview}
        onStartFresh={onStartFresh}
        onAcceptAll={onAcceptAll}
        onImportForReview={onImportForReview}
        onUndo={onUndo}
      />
    </I18nextProvider>,
  );
  return { onImport, onReview, onStartFresh, onAcceptAll, onImportForReview, onUndo };
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

describe('RequoteDiffPanel — assembly offer (M4.13)', () => {
  it('renders no assembly banner unless the server offers it', () => {
    renderPanel();
    expect(screen.queryByTestId('assembly-banner')).not.toBeInTheDocument();
    renderPanel({ assembly_state: { ...offeredState, offered: false } });
    expect(screen.queryByTestId('assembly-banner')).not.toBeInTheDocument();
  });

  it('offers Accept All only while eligible, and only a click imports', () => {
    const { onAcceptAll, onImportForReview } = renderPanel({
      assembly_state: offeredState,
    });
    expect(screen.getByTestId('assembly-banner')).toHaveTextContent('3-mal angeboten');
    expect(onAcceptAll).not.toHaveBeenCalled();
    expect(onImportForReview).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('assembly-accept-all'));
    expect(onAcceptAll).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('assembly-review-import'));
    expect(onImportForReview).toHaveBeenCalledTimes(1);
  });

  it('offers neither import path on a currency mismatch (server rejects both)', () => {
    renderPanel({
      assembly_state: {
        ...offeredState,
        accept_all_eligible: false,
        blockers: ['currency_mismatch'],
      },
    });
    expect(screen.queryByTestId('assembly-accept-all')).not.toBeInTheDocument();
    expect(screen.queryByTestId('assembly-review-import')).not.toBeInTheDocument();
    expect(screen.getByTestId('assembly-import-blocked')).toBeInTheDocument();
  });

  it('suppresses Accept All on a material change — only Review is offered', () => {
    renderPanel({
      assembly_state: {
        ...offeredState,
        accept_all_eligible: false,
        blockers: ['material_changes'],
      },
    });
    expect(screen.queryByTestId('assembly-accept-all')).not.toBeInTheDocument();
    expect(screen.getByTestId('assembly-suppressed')).toBeInTheDocument();
    expect(screen.getByTestId('assembly-review-import')).toBeInTheDocument();
  });

  it('shows the undo chip inside the 60-second window and routes the click', () => {
    const { onUndo } = renderPanel({
      assembly_state: offeredState,
      assembly: {
        path: 'accept_all',
        at: new Date().toISOString(),
        user_id: 'u1',
        source_quote_id: 'q-old',
        source_quote_number: 'Q-2026-1000',
        undone_at: null,
        undo_expires_at: new Date(Date.now() + 55_000).toISOString(),
      },
    });
    // The offer banner is replaced by the audit line once imported.
    expect(screen.queryByTestId('assembly-banner')).not.toBeInTheDocument();
    expect(screen.getByTestId('assembly-imported')).toHaveTextContent('Q-2026-1000');
    fireEvent.click(screen.getByTestId('assembly-undo'));
    expect(onUndo).toHaveBeenCalledTimes(1);
  });

  it('shows the AI-drafted marker (no undo chip) on the Review path', () => {
    renderPanel({
      assembly_state: offeredState,
      assembly: {
        path: 'review',
        at: new Date().toISOString(),
        user_id: 'u1',
        source_quote_id: 'q-old',
        source_quote_number: 'Q-2026-1000',
        undone_at: null,
        undo_expires_at: null,
      },
    });
    expect(screen.getByText('KI-Entwurf — vor dem Versand prüfen')).toBeInTheDocument();
    expect(screen.queryByTestId('assembly-undo')).not.toBeInTheDocument();
  });
});
