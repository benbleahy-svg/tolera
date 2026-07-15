/**
 * Found-in-Files pure model (M3.2 — spec #wingman §2/§5; AI-LENS §4/§8).
 *
 * Groups a file's `ExtractionFinding`s into the Demo-C panel shape — sections
 * (Quote Setup / Requirements / Features / Dimensions) → labelled groups
 * (LENGTHS, ANGLES, FEATURE CONTROL FRAMES, …) → value chips with occurrence
 * counts — and derives the per-section whiteout rects the M2.4 overlay
 * consumes. Regions findings are hidden by default (AI-LENS §4). Pure
 * functions only, so the grouping and the AI-Governor gates are unit-testable.
 */

import type { Rect } from './annotations';
import type { WhiteoutSection } from './redact';

export interface Finding {
  id: string;
  source_file_id: string | null;
  component_id: string | null;
  page: number | null;
  category: 'quote_setup' | 'requirements' | 'features' | 'dimensions' | 'regions';
  type: string;
  raw_text: string | null;
  value: string | null;
  normalized_value: string | null;
  units: string | null;
  tolerance: { kind?: string; upper?: number | string; lower?: number | string } | null;
  role: string | null;
  gdt: { symbol?: string; datum_refs?: string[]; material_condition?: string } | null;
  bbox: Rect | null;
  confidence: number;
  status: 'suggested' | 'accepted' | 'rejected' | 'edited';
}

/**
 * Purple-signal gate (spec #wingman §5: "show purple signal only above a
 * threshold (e.g. ≥ 0.7)") — gates the click-fill dots on Part fields, not
 * the panel listing (all non-rejected findings stay visible for review).
 */
export const AI_SIGNAL_CONFIDENCE_MIN = 0.7;

/** Click-to-fill: finding type → part identity field (spec #wingman §2). */
export const IDENTITY_TYPES = ['part_number', 'revision', 'description'] as const;
export type IdentityType = (typeof IDENTITY_TYPES)[number];

export type Axis = 'size_x' | 'size_y' | 'size_z';

/** Only length-like dimensions may fill a size axis (an angle is not a length). */
export const AXIS_SOURCE_TYPES = ['length', 'diameter', 'radius'] as const;

export type SectionKey = 'quote_setup' | 'requirements' | 'features' | 'dimensions';

export interface ChipGroup {
  /** i18n-ready group label key suffix (lens.group_*), e.g. 'lengths'. */
  key: string;
  chips: Chip[];
}

export interface Chip {
  /** representative finding (actions target it) */
  finding: Finding;
  /** display text for the chip */
  label: string;
  /** occurrences of the same value collapsed into this chip */
  count: number;
}

export interface Section {
  key: SectionKey;
  groups: ChipGroup[];
  findingCount: number;
}

/** Group labels per finding type, in display order (DemoC/02 ground truth). */
const TYPE_GROUPS: Record<SectionKey, [string, (f: Finding) => boolean][]> = {
  quote_setup: [
    ['part_number', (f) => f.type === 'part_number'],
    ['revision', (f) => f.type === 'revision'],
    ['description', (f) => f.type === 'description'],
    ['drawing_number', (f) => f.type === 'drawing_number'],
    ['document_units', (f) => f.type === 'document_units'],
    ['data_control', (f) => f.type === 'export_controlled' || f.type === 'pii'],
    ['tables', (f) => f.type === 'tables' || f.type === 'bom_tables'],
    ['other', () => true],
  ],
  requirements: [
    ['material', (f) => f.type === 'material'],
    ['specifications', (f) => f.type === 'specifications'],
    ['process_keywords', (f) => f.type === 'process_keywords'],
    ['global_tolerances', (f) => f.type === 'global_tolerances'],
    ['flag_notes', (f) => f.type === 'flag_notes'],
    ['other', () => true],
  ],
  features: [
    ['datums', (f) => f.type === 'datum'],
    ['control_frames', (f) => f.type === 'control_frame'],
    ['threads', (f) => f.type === 'thread'],
    ['holes', (f) => f.type === 'hole'],
    ['countersinks', (f) => f.type === 'countersink'],
    ['counterbores', (f) => f.type === 'counterbore'],
    ['chamfers', (f) => f.type === 'chamfer'],
    ['surface_finish', (f) => f.type === 'surface_finish'],
    ['other', () => true],
  ],
  dimensions: [
    ['lengths', (f) => f.type === 'length'],
    ['angles', (f) => f.type === 'angle'],
    ['diameters', (f) => f.type === 'diameter'],
    ['radii', (f) => f.type === 'radius'],
    ['other', () => true],
  ],
};

export const SECTION_ORDER: SectionKey[] = [
  'quote_setup',
  'requirements',
  'features',
  'dimensions',
];

/** The chip's display text: GD&T symbol line when present, else value+units. */
export function chipLabel(finding: Finding): string {
  if (finding.gdt?.symbol) {
    const parts = [finding.gdt.symbol, finding.value ?? finding.raw_text ?? ''];
    if (finding.gdt.datum_refs?.length) parts.push(finding.gdt.datum_refs.join(' | '));
    return parts.filter(Boolean).join(' | ');
  }
  const value = finding.value ?? finding.raw_text ?? '—';
  if (finding.type === 'angle' && !value.includes('°')) return `${value}°`;
  return value;
}

/** Rejected findings are "removed" (spec #wingman §3) — never rendered. */
export function visibleFindings(findings: Finding[]): Finding[] {
  return findings.filter((f) => f.status !== 'rejected' && f.category !== 'regions');
}

/** Panel badge: "Found in files N" counts everything reviewable. */
export function findingsBadgeCount(findings: Finding[]): number {
  return visibleFindings(findings).length;
}

/** Collapse identical labels into one chip with an occurrence count. */
function toChips(findings: Finding[]): Chip[] {
  const byLabel = new Map<string, Chip>();
  for (const finding of findings) {
    const label = chipLabel(finding);
    const existing = byLabel.get(label);
    if (existing) {
      existing.count += 1;
      // A human-touched finding wins the representative slot so the chip
      // renders at full opacity once any duplicate was accepted/edited.
      if (existing.finding.status === 'suggested' && finding.status !== 'suggested') {
        existing.finding = finding;
      }
    } else {
      byLabel.set(label, { finding, label, count: 1 });
    }
  }
  return [...byLabel.values()];
}

/** The Demo-C panel shape: ordered sections → labelled groups → chips. */
export function groupFindings(findings: Finding[]): Section[] {
  const visible = visibleFindings(findings);
  return SECTION_ORDER.map((key) => {
    const inSection = visible.filter((f) => f.category === key);
    const remaining = new Set(inSection);
    const groups: ChipGroup[] = [];
    for (const [groupKey, match] of TYPE_GROUPS[key]) {
      const members = [...remaining].filter(match);
      for (const member of members) remaining.delete(member);
      if (members.length) groups.push({ key: groupKey, chips: toChips(members) });
    }
    return { key, groups, findingCount: inSection.length };
  }).filter((section) => section.findingCount > 0);
}

/**
 * Whiteout / category isolation (block scope-in; DECISIONS.md 2026-07-13
 * M2.4: "M3 Lens callouts plug into the same state"): a toggled-on section
 * contributes its findings' regions as whiteout sections on the print.
 */
export function whiteoutSectionsFor(findings: Finding[], sections: SectionKey[]): WhiteoutSection[] {
  const wanted = new Set<string>(sections);
  return visibleFindings(findings)
    .filter((f) => wanted.has(f.category) && f.bbox && f.page != null)
    .map((f) => ({ id: `lens-${f.id}`, page: f.page as number, rect: f.bbox as Rect }));
}

/**
 * Whether an accept could actually write this finding — mirrors the backend
 * value contract (identity fills use normalized_value||value; an axis fill
 * uses the raw value only). A raw_text-only finding gets no fill affordance:
 * offering one would just 422 server-side.
 */
export function hasFillValue(finding: Finding): boolean {
  if (finding.category === 'dimensions') return finding.value != null;
  return (finding.normalized_value ?? finding.value) != null;
}

/**
 * The best click-fill suggestion for an identity field: highest-confidence
 * *suggested* finding of that type at/above the purple-signal threshold.
 */
export function fillSuggestion(findings: Finding[], type: IdentityType): Finding | null {
  const candidates = findings
    .filter(
      (f) =>
        f.type === type &&
        f.status === 'suggested' &&
        f.confidence >= AI_SIGNAL_CONFIDENCE_MIN &&
        hasFillValue(f),
    )
    .sort((a, b) => b.confidence - a.confidence);
  return candidates[0] ?? null;
}

/** Whether an accept can fill something, and what it needs (axis?). */
export function fillTarget(
  finding: Finding,
): { kind: 'identity'; field: IdentityType } | { kind: 'axis' } | { kind: 'none' } {
  if ((IDENTITY_TYPES as readonly string[]).includes(finding.type)) {
    return { kind: 'identity', field: finding.type as IdentityType };
  }
  if (
    finding.category === 'dimensions' &&
    (AXIS_SOURCE_TYPES as readonly string[]).includes(finding.type)
  ) {
    return { kind: 'axis' };
  }
  return { kind: 'none' };
}
