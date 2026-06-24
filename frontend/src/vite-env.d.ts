/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Clerk frontend key (same value as the backend CLERK_PUBLISHABLE_KEY). Required. */
  readonly VITE_CLERK_PUBLISHABLE_KEY: string;
  /** API origin; empty in dev (the Vite proxy forwards /api → FastAPI). */
  readonly VITE_API_BASE_URL?: string;
  /** BRAND config — parameterised from day one (DECISIONS.md "Product name and domain"). */
  readonly VITE_BRAND_NAME?: string;
  readonly VITE_BRAND_SHORT_NAME?: string;
  readonly VITE_BRAND_DOMAIN?: string;
  readonly VITE_BRAND_APP_DOMAIN?: string;
  readonly VITE_BRAND_RFQ_DOMAIN?: string;
  readonly VITE_BRAND_LOGO_URL?: string;
  readonly VITE_BRAND_PRIMARY_COLOR?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
