/**
 * Exact per-unit division for the API's 4-dp decimal-string money values
 * (display only — the wire contract stays numeric(14,4) strings per the
 * resolved 2026-06-27 money decision). BigInt arithmetic, ROUND_HALF_UP to
 * 4 dp — never a float, so the shown per-unit value is deterministic.
 */
/** "123.45" → signed BigInt in 1e-4 units; null for malformed input. */
function toUnits(value: string): bigint | null {
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

export function perUnitExact(value: string | null, quantity: number): string | null {
  if (value == null || !Number.isInteger(quantity) || quantity <= 0) return null;
  const units = toUnits(value);
  if (units == null) return null;
  // divide half-up on the magnitude
  const magnitude = units < 0n ? -units : units;
  const q = BigInt(quantity);
  const perUnit = (2n * magnitude + q) / (2n * q);
  return fromUnits(units < 0n ? -perUnit : perUnit);
}

/** Exact 4-dp sum; nulls/malformed entries are skipped. Returns null only
 * when `nullIfEmpty` and nothing was summable. */
export function sumExact(values: (string | null | undefined)[], nullIfEmpty = false): string | null {
  let total = 0n;
  let seen = false;
  for (const value of values) {
    if (value == null) continue;
    const units = toUnits(value);
    if (units == null) continue;
    total += units;
    seen = true;
  }
  if (!seen && nullIfEmpty) return null;
  return fromUnits(total);
}
