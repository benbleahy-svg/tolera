/**
 * de-DE catalog guard (M5.9). Two invariants the "consolidated German" exit
 * clause depends on:
 *  1. de/en key parity — every key present in one locale exists in the other, so
 *     a German surface never silently falls back to an English (or missing) key.
 *  2. Locale-correct money — DE/AT comma-decimal `1.234,56 €`; CH point-decimal +
 *     apostrophe `CHF 1'234.56` (special-cased via `localeForCurrency`, NOT the
 *     de-DE formatter) — DACH-DELTA §1 "CH is the trap".
 */

import { describe, expect, it } from 'vitest';

import { formatMinor, formatMoney, localeForCurrency } from '../portal/money';
import de from './locales/de.json';
import en from './locales/en.json';

function flatKeys(obj: unknown, prefix = ''): string[] {
  if (obj === null || typeof obj !== 'object') return [prefix];
  return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
    flatKeys(v, prefix ? `${prefix}.${k}` : k),
  );
}

/** Every leaf value with its key path — including non-strings, so the guard can
 *  reject them (a numeric/boolean/null/empty-object leaf is a malformed catalog). */
function flatValues(obj: unknown, prefix = ''): [string, unknown][] {
  if (obj !== null && typeof obj === 'object' && Object.keys(obj).length > 0) {
    return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
      flatValues(v, prefix ? `${prefix}.${k}` : k),
    );
  }
  return [[prefix, obj]];
}

/** Collapse NBSP / narrow-NBSP to a plain space so exact-string assertions are
 *  stable across ICU builds (de-DE/de-CH use U+00A0 / U+202F around the symbol). */
function normalizeSpaces(value: string): string {
  return value.replace(/[\u00A0\u202F]/g, " ");
}

describe('i18n catalog parity', () => {
  it('has identical key sets in de and en (no missing-key fallbacks)', () => {
    const deKeys = new Set(flatKeys(de));
    const enKeys = new Set(flatKeys(en));
    const missingInDe = [...enKeys].filter((k) => !deKeys.has(k));
    const missingInEn = [...deKeys].filter((k) => !enKeys.has(k));
    expect(missingInDe).toEqual([]);
    expect(missingInEn).toEqual([]);
  });

  it('has only non-empty string German values (no null/number/empty-object leaves)', () => {
    const invalid = flatValues(de)
      .filter(([, v]) => typeof v !== 'string' || v.trim() === '')
      .map(([k]) => k);
    expect(invalid).toEqual([]);
  });
});

describe('DACH money formatting', () => {
  it('formats EUR de-DE with comma decimal, dot grouping, trailing symbol', () => {
    expect(localeForCurrency('EUR')).toBe('de-DE');
    expect(normalizeSpaces(formatMinor(123456, 'EUR'))).toBe('1.234,56 €');
  });

  it('formats CHF with point decimal + apostrophe grouping (special-cased, not de-DE)', () => {
    expect(localeForCurrency('CHF')).toBe('de-CH');
    expect(normalizeSpaces(formatMinor(123456, 'CHF'))).toBe("CHF 1'234.56");
  });

  it('formatMoney (4-dp string path) applies the same CH special-casing', () => {
    expect(normalizeSpaces(formatMoney('1234.56', 'CHF'))).toBe("CHF 1'234.56");
    expect(normalizeSpaces(formatMoney('1234.56', 'EUR'))).toBe('1.234,56 €');
  });
});
