/**
 * Routes. Each primary-nav destination renders inside the persistent `AppShell`;
 * the destination screens themselves arrive in later blocks (placeholder for
 * now). Sign-out is wired here (the only Clerk touch-point below the auth gate)
 * and handed to the shell.
 */

import { useClerk } from '@clerk/clerk-react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { CustomTablesPage } from './configure/CustomTablesPage';
import { OperationsPage } from './configure/OperationsPage';
import { PricingDefsPage } from './configure/PricingDefsPage';
import { AccountDetailPage } from './contacts/AccountDetailPage';
import { ContactDetailPage } from './contacts/ContactDetailPage';
import { ContactsPage } from './contacts/ContactsPage';
import { EstimatingPage } from './estimating/EstimatingPage';
import { PartsPage } from './parts/PartsPage';
import { PdfViewerPage } from './viewer/PdfViewerPage';
import { QuotesPage } from './quotes/QuotesPage';
import { PlaceholderPage } from './pages/PlaceholderPage';
import { AppShell } from './shell/AppShell';
import { NAV_ITEMS } from './shell/nav';

/** Nav destinations that have a real screen; the rest render a placeholder. */
const REAL_ROUTES = new Set(['/contacts', '/parts', '/quotes', '/configure']);

export default function App() {
  const { signOut } = useClerk();

  return (
    <Routes>
      <Route element={<AppShell onSignOut={() => void signOut()} />}>
        {/* Contacts (M1.1) and Parts (M1.2) are real destinations; the others
            stay placeholders until their block lands. */}
        {NAV_ITEMS.filter((item) => !REAL_ROUTES.has(item.to)).map(({ to, labelKey }) => (
          <Route key={to} path={to} element={<PlaceholderPage titleKey={labelKey} />} />
        ))}
        <Route path="/contacts" element={<ContactsPage />} />
        <Route path="/contacts/:accountId" element={<AccountDetailPage />} />
        <Route path="/contacts/:accountId/contacts/:contactId" element={<ContactDetailPage />} />
        <Route path="/parts" element={<PartsPage />} />
        <Route path="/parts/:partId/files/:fileId/view" element={<PdfViewerPage />} />
        <Route path="/quotes" element={<QuotesPage />} />
        {/* Line-item estimating view — the M1.7 Materials & Operations slice. */}
        <Route path="/quotes/:quoteId" element={<EstimatingPage />} />
        {/* Configure lands on Custom Tables (M1.9); the full Configure section
            (operation library pages, …) grows a sub-nav with M1.12. */}
        <Route path="/configure" element={<CustomTablesPage />} />
        {/* Configure → Pricing: the org pricing-item/discount library (M1.10). */}
        <Route path="/configure/pricing" element={<PricingDefsPage />} />
        <Route path="/configure/operations" element={<OperationsPage />} />
        {/* Unknown paths redirect home rather than rendering the dashboard at a
            wrong URL (keeps the landing route distinct from the catch-all). */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
