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

/** Minimum decimal places for mass — see module note (grams on small parts). */
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

/**
 * How one quantity converts + labels in each system. The base value (mm, mm²,
 * mm³, kg) is multiplied by the active system's factor and suffixed with its
 * unit — the single knob that removes the metric/imperial branch from every
 * format function.
 */
interface UnitSpec {
  metricFactor: number;
  metricUnit: string;
  imperialFactor: number;
  imperialUnit: string;
}

const LENGTH: UnitSpec = { metricFactor: 1, metricUnit: 'mm', imperialFactor: 1 / MM_PER_IN, imperialUnit: 'in' };
const AREA: UnitSpec = { metricFactor: 1, metricUnit: 'mm²', imperialFactor: 1 / MM2_PER_IN2, imperialUnit: 'in²' };
const VOLUME: UnitSpec = { metricFactor: 1 / MM3_PER_CM3, metricUnit: 'cm³', imperialFactor: 1 / MM3_PER_IN3, imperialUnit: 'in³' };
const MASS: UnitSpec = { metricFactor: 1, metricUnit: 'kg', imperialFactor: LB_PER_KG, imperialUnit: 'lb' };

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

function precision(opts: DisplayOptions): number {
  return opts.precision ?? 2;
}

/** Convert a base-unit value to the active system, format it, and append the unit. */
function formatQuantity(
  base: number | null,
  opts: DisplayOptions,
  spec: UnitSpec,
  digits: number,
): string {
  const imperial = (opts.system ?? 'metric') === 'imperial';
  const value = base != null ? base * (imperial ? spec.imperialFactor : spec.metricFactor) : null;
  const formatted = fixed(value, opts.language, digits);
  return formatted != null ? `${formatted} ${imperial ? spec.imperialUnit : spec.metricUnit}` : EM_DASH;
}

export function formatLength(mm: number | null, opts: DisplayOptions): string {
  return formatQuantity(mm, opts, LENGTH, precision(opts));
}

export function formatArea(mm2: number | null, opts: DisplayOptions): string {
  return formatQuantity(mm2, opts, AREA, precision(opts));
}

export function formatVolume(mm3: number | null, opts: DisplayOptions): string {
  return formatQuantity(mm3, opts, VOLUME, precision(opts));
}

export function formatMass(kg: number | null, opts: DisplayOptions): string {
  return formatQuantity(kg, opts, MASS, Math.max(precision(opts), MASS_DECIMAL_FLOOR));
}

export function formatAngle(deg: number | null, opts: DisplayOptions): string {
  // Angle is unitless across systems and always whole degrees (precision-exempt).
  return fixed(deg, opts.language, 0)?.concat('°') ?? EM_DASH;
}

/**
 * A measured distance with the M2.8 exact-vs-approximate trust signal: an
 * `exact` result (special orientation — parallel planes / concentric cylinders /
 * perpendicular cyl+plane) prints bare; anything else gets a leading `~` to
 * flag it as approximate. See `measure.ts` and DECISIONS.md [2026-07-14].
 */
export function formatMeasureDistance(mm: number | null, exact: boolean, language: string): string {
  const value = formatLength(mm, language);
  if (value === EM_DASH) return value;
  return exact ? value : `~${value}`;
}
