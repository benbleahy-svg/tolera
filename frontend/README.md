# Tolera frontend

The Tolera web client — React 19 + TypeScript + Vite. The app shell (sidebar
navigation, i18n, theming, org-switcher) lands in build block **M0.4**; the
authoritative UI spec is `docs/spec/Bid-Factory-Build-Spec.html` (`#ui-system`,
`#shell`).

## Layout

```
src/
  brand.ts            BRAND config (product name/domains/logo/colour) — parameterised,
                      no hardcoded product strings (DECISIONS.md "Product name and domain")
  theme/              light+dark design tokens (index.css) + mode apply/persist (theme.ts)
  i18n/               i18next setup + de/en catalogs (German-first, de-DE default)
  api/client.ts       fetch wrapper that injects the Clerk bearer token
  session/            SessionContext + SessionProvider (loads GET /api/me)
  shell/              Sidebar, AccountMenu, OrgSwitcher, nav config, inline-SVG icons
  pages/              routed placeholder pages (real screens arrive in later blocks)
  test/               vitest setup + a Clerk-free render helper
```

## Commands

```bash
npm install
npm run dev        # Vite dev server on :5173, proxies /api → FastAPI (:8000)
npm run lint       # oxlint
npm run test       # vitest (component/integration)
npm run build      # tsc -b && vite build
```

## Configuration

Copy `.env.example` → `.env` and set `VITE_CLERK_PUBLISHABLE_KEY` (same value as
the backend `CLERK_PUBLISHABLE_KEY`). `VITE_BRAND_*` overrides default to Tolera.
In dev, `VITE_API_BASE_URL` can stay empty — the Vite proxy forwards `/api`.

## Auth & data

The shell renders only when authenticated (Clerk); on load it fetches
`GET /api/me` for the user, active org, memberships, and effective permissions,
and gates navigation on those capabilities. A full logged-in render needs a
seeded, Clerk-synced user — wired in M0.5 (seed) + M5.12 (Clerk↔membership sync).
