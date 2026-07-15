import { describe, expect, it } from 'vitest';

import { perUnitExact, sumExact } from './money';

describe('sumExact', () => {
  it('sums 4-dp strings exactly (no float drift)', () => {
    // 0.1 + 0.2 famously drifts in floats
    expect(sumExact(['0.1000', '0.2000'])).toBe('0.3000');
    expect(sumExact(['539.3680', '134.8400'])).toBe('674.2080');
  });

  it('skips nulls; empty behavior is caller-controlled', () => {
    expect(sumExact([null, '5.0000', undefined])).toBe('5.0000');
    expect(sumExact([], true)).toBeNull();
    expect(sumExact([])).toBe('0.0000');
  });

  it('handles negatives', () => {
    expect(sumExact(['10.0000', '-2.5000'])).toBe('7.5000');
  });
});

describe('perUnitExact', () => {
  it('divides 4-dp strings exactly', () => {
    expect(perUnitExact('160.0000', 10)).toBe('16.0000');
    expect(perUnitExact('539.3680', 1)).toBe('539.3680');
    expect(perUnitExact('100', 3)).toBe('33.3333');
  });

  it('rounds half-up at the 4th decimal', () => {
    expect(perUnitExact('0.0001', 2)).toBe('0.0001'); // 0.00005 → up
    expect(perUnitExact('0.0001', 3)).toBe('0.0000');
  });

  it('handles values beyond float precision without drift', () => {
    expect(perUnitExact('90071992547409.9312', 2)).toBe('45035996273704.9656');
  });

  it('keeps the sign', () => {
    expect(perUnitExact('-10.0000', 4)).toBe('-2.5000');
  });

  it('returns null for null, malformed input, or a non-positive quantity', () => {
    expect(perUnitExact(null, 5)).toBeNull();
    expect(perUnitExact('abc', 5)).toBeNull();
    expect(perUnitExact('10.0', 0)).toBeNull();
    expect(perUnitExact('10.0', 2.5)).toBeNull();
  });
});
