/**
 * BRAND configuration — the single source of every customer-facing product
 * name, domain, logo, and brand colour. Parameterised from day one so the
 * product can be white-labelled / renamed with **zero code edits** (DECISIONS.md
 * 2026-06-14 "Product name and domain"). Nothing in the UI hardcodes "Tolera";
 * everything reads `BRAND`. Values come from build-time `VITE_BRAND_*` env, with
 * the Tolera defaults baked in.
 */

export interface Brand {
  /** Full product name shown in the UI (e.g. the sidebar wordmark, page title). */
  readonly name: string;
  /** Compact mark for the collapsed sidebar (1–2 glyphs). */
  readonly shortName: string;
  readonly domains: {
    readonly marketing: string;
    readonly app: string;
    readonly rfq: string;
  };
  /** Logo asset URL, or null to fall back to the text wordmark. */
  readonly logoUrl: string | null;
  /** Optional primary-colour override; empty string = use the design-token default. */
  readonly primaryColor: string;
}

const env = import.meta.env;

export const BRAND: Brand = {
  name: env.VITE_BRAND_NAME ?? 'Tolera',
  shortName: env.VITE_BRAND_SHORT_NAME ?? 'T',
  domains: {
    marketing: env.VITE_BRAND_DOMAIN ?? 'tolera.eu',
    app: env.VITE_BRAND_APP_DOMAIN ?? 'app.tolera.eu',
    rfq: env.VITE_BRAND_RFQ_DOMAIN ?? 'rfq.tolera.eu',
  },
  // `||` (not `??`): a blank VITE_BRAND_LOGO_URL must fall back to the wordmark.
  logoUrl: env.VITE_BRAND_LOGO_URL || null,
  primaryColor: env.VITE_BRAND_PRIMARY_COLOR ?? '',
};

/**
 * Apply brand-level overrides to the design tokens at startup. A configured
 * primary colour overrides the `--p` token everywhere it is consumed — so a
 * white-label colour change is config-only (the per-tenant re-theming seam the
 * token architecture is built for). Empty = keep the Claude default.
 */
export function applyBrand(brand: Brand = BRAND): void {
  if (brand.primaryColor) {
    document.documentElement.style.setProperty('--p', brand.primaryColor);
  }
}
