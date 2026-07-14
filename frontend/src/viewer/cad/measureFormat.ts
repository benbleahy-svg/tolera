/**
 * Display formatting for selection-data / whole-file readout numbers.
 *
 * Geometry is computed in base model units (mm, mm², mm³, kg, deg); this layer
 * owns the DACH presentation choice — mm / mm² / cm³ / kg / deg, comma-decimal
 * per locale, never imperial (DACH-DELTA §6). Decimal precision is fixed here
 * for M2.7; the user-configurable precision gear arrives in M2.9.
 */
const EM_DASH = '—';

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

export function formatLength(mm: number | null, language: string): string {
  return fixed(mm, language, 2)?.concat(' mm') ?? EM_DASH;
}

export function formatArea(mm2: number | null, language: string): string {
  return fixed(mm2, language, 2)?.concat(' mm²') ?? EM_DASH;
}

export function formatVolume(mm3: number | null, language: string): string {
  if (mm3 == null || !Number.isFinite(mm3)) return EM_DASH;
  return `${fixed(mm3 / 1000, language, 2)} cm³`;
}

export function formatMass(kg: number | null, language: string): string {
  return fixed(kg, language, 3)?.concat(' kg') ?? EM_DASH;
}

export function formatAngle(deg: number | null, language: string): string {
  return fixed(deg, language, 0)?.concat('°') ?? EM_DASH;
}
