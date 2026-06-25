import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider, RedirectToSignIn, SignedIn, SignedOut } from '@clerk/clerk-react'
import { I18nextProvider } from 'react-i18next'
import { BrowserRouter } from 'react-router-dom'

import App from './App.tsx'
import { applyBrand, BRAND } from './brand'
import i18n from './i18n'
import { SessionProvider } from './session/SessionProvider'
import { applyMode, getInitialMode } from './theme/theme'
import './index.css'
import './styles/shell.css'
import './styles/contacts.css'

// Apply the persisted colour mode + brand (title + colour token) before first paint.
applyMode(getInitialMode())
applyBrand()
document.title = BRAND.name

// Fail fast on a config error rather than handing '' to ClerkProvider (which
// would surface as an opaque runtime failure).
const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY
if (!publishableKey) {
  // German-first, even for this pre-render config error (frontend coding guideline).
  throw new Error('VITE_CLERK_PUBLISHABLE_KEY fehlt — in frontend/.env setzen (siehe .env.example)')
}

createRoot(document.getElementById('root')!).render(
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
