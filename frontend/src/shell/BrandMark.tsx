/**
 * The product wordmark/logo (home). Reads everything from `BRAND` — no hardcoded
 * product name — so a rename/white-label is config-only (DECISIONS.md
 * "Product name and domain").
 */

import { BRAND } from '../brand';

export function BrandMark({ collapsed }: { collapsed: boolean }) {
  return (
    <span className="brand-mark" title={BRAND.name} aria-label={BRAND.name}>
      {BRAND.logoUrl ? (
        <img className="brand-logo" src={BRAND.logoUrl} alt={BRAND.name} />
      ) : (
        <span className="brand-glyph" aria-hidden="true">
          {BRAND.shortName}
        </span>
      )}
      {!collapsed && <span className="brand-name">{BRAND.name}</span>}
    </span>
  );
}
