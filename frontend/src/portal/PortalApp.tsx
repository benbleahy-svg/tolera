/**
 * Public buyer-portal router (M5.1). Rendered on the `/q/*` branch of main.tsx
 * with NO Clerk / session / AppShell — the page is unauthenticated and
 * white-label. Only the Digital Quote route lives here; anything else is an
 * invalid link.
 */

import { useTranslation } from 'react-i18next';
import { Route, Routes } from 'react-router-dom';

import { BuyerPortalPage } from './BuyerPortalPage';

function InvalidLink() {
  const { t } = useTranslation();
  return (
    <div className="portal-state portal-error" role="alert">
      <p>{t('portal.invalid_link')}</p>
    </div>
  );
}

export function PortalApp() {
  return (
    <Routes>
      <Route path="/q/:token" element={<BuyerPortalPage />} />
      <Route path="*" element={<InvalidLink />} />
    </Routes>
  );
}
