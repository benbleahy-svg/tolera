/**
 * Display formatting for selection-data / whole-file readout numbers.
 *
 * Geometry is computed in base model units (mm, mm², mm³, kg, deg); this layer
 * owns the presentation choice. M2.9 adds the display-options gear: a
 * metric↔imperial unit system and a user decimal-precision, both applied live.
 *
 * The DACH default stays metric — mm / mm² / cm³ / kg / deg, comma-decimal per
 * locale, never imperial by default (DACH-DELTA §6): the toggle exists but a
 * fresh viewer always opens `{ system: 'metric', precision: 2 }`. Angle is
 * always whole degrees; mass keeps a 3-decimal floor (grams matter on small
 * parts) so the precision slider can only add digits to it, never drop grams.
 */
const EM_DASH = '—';

/** mm-based conversion factors to imperial (exact by definition of the inch). */
const MM_PER_IN = 25.4;
const MM2_PER_IN2 = MM_PER_IN * MM_PER_IN; // 645.16
const MM3_PER_IN3 = MM_PER_IN * MM_PER_IN * MM_PER_IN; // 16387.064
const MM3_PER_CM3 = 1000;
const LB_PER_KG = 2.2046226218;

/** Whole-degree precision floor for mass — see module note. */
const MASS_DECIMAL_FLOOR = 3;

export type UnitSystem = 'metric' | 'imperial';

/**
 * Presentation options for the readout numbers. Only `language` is required;
 * `system` and `precision` default to the DACH-native metric preset so callers
 * that don't set the gear get the safe default.
 */
export interface DisplayOptions {
  language: string;
  /** Unit system; defaults to metric (never imperial by default — DACH §6). */
  system?: UnitSystem;
  /** Decimal places for length/area/volume; defaults to 2. */
  precision?: number;
}

/** Map the app's i18n language to a number-formatting locale (comma vs point). */
function localeTag(language: string): string {
  return language.startsWith('de') ? 'de-DE' : 'en-IE';
}

function fixed(value: number | null, language: string, digits: number): string | null {
  if (value == null || !Number.isFinite(value)) return null;
  return new Intl.NumberFormat(localeTag(language), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function system(opts: DisplayOptions): UnitSystem {
  return opts.system ?? 'metric';
}

function precision(opts: DisplayOptions): number {
  return opts.precision ?? 2;
}

export function formatLength(mm: number | null, opts: DisplayOptions): string {
  const imperial = system(opts) === 'imperial';
  const value = mm != null ? (imperial ? mm / MM_PER_IN : mm) : null;
  return fixed(value, opts.language, precision(opts))?.concat(imperial ? ' in' : ' mm') ?? EM_DASH;
}

export function formatArea(mm2: number | null, opts: DisplayOptions): string {
  const imperial = system(opts) === 'imperial';
  const value = mm2 != null ? (imperial ? mm2 / MM2_PER_IN2 : mm2) : null;
  return (
    fixed(value, opts.language, precision(opts))?.concat(imperial ? ' in²' : ' mm²') ?? EM_DASH
  );
}

export function formatVolume(mm3: number | null, opts: DisplayOptions): string {
  if (mm3 == null || !Number.isFinite(mm3)) return EM_DASH;
  const imperial = system(opts) === 'imperial';
  const value = imperial ? mm3 / MM3_PER_IN3 : mm3 / MM3_PER_CM3;
  return `${fixed(value, opts.language, precision(opts))} ${imperial ? 'in³' : 'cm³'}`;
}

export function formatMass(kg: number | null, opts: DisplayOptions): string {
  const imperial = system(opts) === 'imperial';
  const value = kg != null ? (imperial ? kg * LB_PER_KG : kg) : null;
  const digits = Math.max(precision(opts), MASS_DECIMAL_FLOOR);
  return fixed(value, opts.language, digits)?.concat(imperial ? ' lb' : ' kg') ?? EM_DASH;
}

export function formatAngle(deg: number | null, opts: DisplayOptions): string {
  // Angle is unitless across systems and always whole degrees (precision-exempt).
  return fixed(deg, opts.language, 0)?.concat('°') ?? EM_DASH;
}
