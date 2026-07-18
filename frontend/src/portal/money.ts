/**
 * Buyer-portal money formatting. The public endpoint returns 4-dp decimal
 * STRINGS (e.g. "200.0000") or null. The portal is German-first regardless of
 * any UI language toggle: CHF renders `de-CH` (CHF 1'234.56), everything else
 * `de-DE` (1.234,56 €). Null renders an em dash. Summation stays exact via
 * integer 1e-4 units — never a float — so the live subtotal is deterministic.
 */

const EM_DASH = '—';

/** "123.45" → signed BigInt in 1e-4 units; null for null/malformed input. */
function toUnits(value: string | null): bigint | null {
  if (value == null) return null;
  const match = /^(-?)(\d+)(?:\.(\d{1,4}))?$/.exec(value.trim());
  if (!match) return null;
  const [, sign, whole, frac = ''] = match;
  const units = BigInt(whole + frac.padEnd(4, '0'));
  return sign === '-' ? -units : units;
}

function fromUnits(units: bigint): string {
  const sign = units < 0n ? '-' : '';
  const magnitude = units < 0n ? -units : units;
  return `${sign}${magnitude / 10000n}.${(magnitude % 10000n).toString().padStart(4, '0')}`;
}

/** Locale for a currency: CHF → de-CH, else de-DE (German-first portal). */
export function localeForCurrency(currency: string): string {
  return currency === 'CHF' ? 'de-CH' : 'de-DE';
}

/** Format a 4-dp decimal string as a locale currency string; null → em dash. */
export function formatMoney(value: string | null, currency: string): string {
  if (value == null) return EM_DASH;
  const num = Number(value);
  if (Number.isNaN(num)) return EM_DASH;
  return new Intl.NumberFormat(localeForCurrency(currency), {
    style: 'currency',
    currency,
  }).format(num);
}

/** Format integer minor units (cents/Rappen) as a locale currency string. The
 *  checkout/order endpoints emit money as minor units, not 4-dp strings. */
export function formatMinor(minor: number, currency: string): string {
  return new Intl.NumberFormat(localeForCurrency(currency), {
    style: 'currency',
    currency,
  }).format(minor / 100);
}

/** Exact 4-dp sum of decimal strings; nulls/malformed entries are skipped. */
export function sumMoney(values: (string | null | undefined)[]): string {
  let total = 0n;
  for (const value of values) {
    const units = toUnits(value ?? null);
    if (units != null) total += units;
  }
  return fromUnits(total);
}
