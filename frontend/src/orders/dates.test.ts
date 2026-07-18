import { describe, expect, it } from 'vitest';

import { formatOrderDate } from './dates';

describe('formatOrderDate', () => {
  it('renders a date-only value as its calendar date (no UTC shift)', () => {
    // new Date("2026-07-15") is UTC midnight → would show the 14th west of UTC.
    // The local-calendar parse keeps the day at 15 in every timezone (the guard);
    // the exact separator/zero-padding is ICU-dependent, so assert day + year.
    const out = formatOrderDate('2026-07-15', 'de-DE');
    expect(out).toMatch(/^15\./); // day is 15, never 14
    expect(out).toContain('2026');
  });

  it('renders a full timestamp as a local date', () => {
    // 10:00Z lands on the same calendar day for any realistic timezone.
    const out = formatOrderDate('2026-07-15T10:00:00Z', 'de-DE');
    expect(out).toMatch(/^15\./);
    expect(out).toContain('2026');
  });

  it('renders null / empty as an em dash', () => {
    expect(formatOrderDate(null, 'de-DE')).toBe('—');
    expect(formatOrderDate('', 'de-DE')).toBe('—');
  });
});
