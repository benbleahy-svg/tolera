/**
 * Public vendor-RFQ router (M6.2). Rendered on the `/vendor-rfq/*` branch of
 * main.tsx with NO Clerk / session / AppShell — the page is unauthenticated and
 * white-label, exactly like the buyer portal. Only the RFQ response route lives
 * here; anything else is an invalid link.
 */

import { useTranslation } from 'react-i18next';
import { Route, Routes } from 'react-router-dom';

import { VendorRfqPage } from './VendorRfqPage';

function InvalidLink() {
  const { t } = useTranslation();
  return (
    <div className="portal-state portal-error" role="alert">
      <p>{t('vendorPortal.invalid_link')}</p>
    </div>
  );
}

export function VendorPortalApp() {
  return (
    <Routes>
      <Route path="/vendor-rfq/:token" element={<VendorRfqPage />} />
      <Route path="*" element={<InvalidLink />} />
    </Routes>
  );
}
