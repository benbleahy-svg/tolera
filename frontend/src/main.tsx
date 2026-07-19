import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider, RedirectToSignIn, SignedIn, SignedOut } from '@clerk/clerk-react'
import { I18nextProvider } from 'react-i18next'
import { BrowserRouter } from 'react-router-dom'

import App from './App.tsx'
import { applyBrand, BRAND } from './brand'
import i18n from './i18n'
import { PortalApp } from './portal/PortalApp'
import { VendorPortalApp } from './vendor-portal/VendorPortalApp'
import { SessionProvider } from './session/SessionProvider'
import { applyMode, getInitialMode } from './theme/theme'
import './index.css'
import './styles/shell.css'
import './styles/contacts.css'
import './styles/parts.css'
import './styles/quotes.css'
import './styles/orders.css'
import './styles/estimating.css'
import './styles/collab.css'
import './styles/configure.css'
import './styles/lens.css'
import './styles/review.css'
import './styles/bom.css'
import './styles/portal.css'
import './styles/vendor-portal.css'

// Apply the persisted colour mode + brand (title + colour token) before first paint.
applyMode(getInitialMode())
applyBrand()
document.title = BRAND.name

const root = createRoot(document.getElementById('root')!)

// The public, unauthenticated portals — the buyer's Digital Quote (`/q/:token`,
// M5.1) and the vendor's RFQ response form (`/vendor-rfq/:token`, M6.2) — render
// SEPARATE trees with NO Clerk / session / AppShell; they must never read the
// Clerk publishable key. Everything else is the authenticated app.
const publicTree = window.location.pathname.startsWith('/q/')
  ? <PortalApp />
  : window.location.pathname.startsWith('/vendor-rfq/')
    ? <VendorPortalApp />
    : null

if (publicTree) {
  root.render(
    <StrictMode>
      <I18nextProvider i18n={i18n}>
        <BrowserRouter>
          {publicTree}
        </BrowserRouter>
      </I18nextProvider>
    </StrictMode>,
  )
} else {
  // Fail fast on a config error rather than handing '' to ClerkProvider (which
  // would surface as an opaque runtime failure).
  const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY
  if (!publishableKey) {
    // German-first, even for this pre-render config error (frontend coding guideline).
    throw new Error('VITE_CLERK_PUBLISHABLE_KEY fehlt — in frontend/.env setzen (siehe .env.example)')
  }

  root.render(
    <StrictMode>
      <ClerkProvider publishableKey={publishableKey} afterSignOutUrl="/">
        <I18nextProvider i18n={i18n}>
          {/* The shell renders only when authenticated; otherwise Clerk redirects to sign-in. */}
          <SignedIn>
            <SessionProvider>
              <BrowserRouter>
                <App />
              </BrowserRouter>
            </SessionProvider>
          </SignedIn>
          <SignedOut>
            <RedirectToSignIn />
          </SignedOut>
        </I18nextProvider>
      </ClerkProvider>
    </StrictMode>,
  )
}
