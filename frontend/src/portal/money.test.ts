/**
 * Buyer-portal money formatting (M5.1): German-first — EUR renders de-DE
 * (comma decimals, € symbol), CHF renders de-CH (dot decimals, CHF code),
 * null renders an em dash; summation stays exact.
 */

import { describe, expect, it } from 'vitest';

import { formatMoney, sumMoney } from './money';

describe('formatMoney', () => {
  it('formats EUR with the de-DE convention', () => {
    const out = formatMoney('200.0000', 'EUR');
    expect(out).toContain('200,00');
    expect(out).toContain('€');
  });

  it('formats CHF with the de-CH convention', () => {
    const out = formatMoney('200.5000', 'CHF');
    expect(out).toContain('CHF');
    expect(out).toContain('200.50');
  });

  it('renders an em dash for null', () => {
    expect(formatMoney(null, 'EUR')).toBe('—');
  });

  it('renders an em dash for a malformed value', () => {
    expect(formatMoney('n/a', 'EUR')).toBe('—');
  });
});

describe('sumMoney', () => {
  it('sums 4-dp decimal strings exactly, skipping nulls', () => {
    expect(sumMoney(['100.0000', '50.5000', null, undefined])).toBe('150.5000');
  });

  it('returns zero for an empty selection', () => {
    expect(sumMoney([])).toBe('0.0000');
  });
});
