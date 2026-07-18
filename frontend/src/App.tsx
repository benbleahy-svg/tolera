/**
 * Routes. Each primary-nav destination renders inside the persistent `AppShell`;
 * the destination screens themselves arrive in later blocks (placeholder for
 * now). Sign-out is wired here (the only Clerk touch-point below the auth gate)
 * and handed to the shell.
 */

import { useClerk } from '@clerk/clerk-react';
import { Navigate, Route, Routes, useParams } from 'react-router-dom';

import { CustomTablesPage } from './configure/CustomTablesPage';
import { OperationsPage } from './configure/OperationsPage';
import { PricingDefsPage } from './configure/PricingDefsPage';
import { RulesPage } from './configure/RulesPage';
import { InterrogationsPage } from './configure/InterrogationsPage';
import { AccountDetailPage } from './contacts/AccountDetailPage';
import { ContactDetailPage } from './contacts/ContactDetailPage';
import { ContactsPage } from './contacts/ContactsPage';
import { DashboardPage } from './dashboard/DashboardPage';
import { EstimatingPage } from './estimating/EstimatingPage';
import { NestingPage } from './estimating/NestingPage';
import { PartsPage } from './parts/PartsPage';
import { FileViewerPage } from './viewer/FileViewerPage';
import { QuotesPage } from './quotes/QuotesPage';
import { OrdersPage } from './orders/OrdersPage';
import { OrderDetailPage } from './orders/OrderDetailPage';
import { PlaceholderPage } from './pages/PlaceholderPage';
import { EmailConnectionPage } from './settings/EmailConnectionPage';
import { EmailTemplatesPage } from './settings/EmailTemplatesPage';
import { AppShell } from './shell/AppShell';
import { NAV_ITEMS } from './shell/nav';

/** Nav destinations that have a real screen; the rest render a placeholder. */
const REAL_ROUTES = new Set(['/', '/contacts', '/parts', '/quotes', '/orders', '/configure']);

/**
 * M5.0 — the estimating screen moved to the spec route `/quotes/edit/:id/:lineItemId`.
 * The old `/quotes/:quoteId` links keep working: this forwards to the new shape, where
 * `EstimatingPage` resolves the first line item (client "301" — no server in an SPA).
 */
function EstimatingRedirect() {
  const { quoteId } = useParams<{ quoteId: string }>();
  return <Navigate to={`/quotes/edit/${quoteId}`} replace />;
}

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
        <Route path="/" element={<DashboardPage />} />
        <Route path="/contacts" element={<ContactsPage />} />
        <Route path="/contacts/:accountId" element={<AccountDetailPage />} />
        <Route path="/contacts/:accountId/contacts/:contactId" element={<ContactDetailPage />} />
        <Route path="/parts" element={<PartsPage />} />
        <Route path="/parts/:partId/files/:fileId/view" element={<FileViewerPage />} />
        <Route path="/quotes" element={<QuotesPage />} />
        {/* Line-item estimating view at the spec route (M5.0, #partview): a left
            line-item sidebar + the costing-inputs band. `/quotes/edit/:id` (no line
            item) forwards to the first item; the old `/quotes/:quoteId` 301-redirects. */}
        <Route path="/quotes/edit/:id/:lineItemId" element={<EstimatingPage />} />
        <Route path="/quotes/edit/:id" element={<EstimatingPage />} />
        <Route path="/quotes/:quoteId" element={<EstimatingRedirect />} />
        {/* Multi-component sheet-metal nesting (M4.3, spec #nesting). */}
        <Route path="/quotes/:quoteId/nesting" element={<NestingPage />} />
        {/* Orders tab — list + detail (M5.6, #orderslist). No create route: orders
            come only from checkout (M5.2) or Build Order (M5.7). */}
        <Route path="/orders" element={<OrdersPage />} />
        <Route path="/orders/:orderId" element={<OrderDetailPage />} />
        {/* Configure lands on Custom Tables (M1.9); the full Configure section
            (operation library pages, …) grows a sub-nav with M1.12. */}
        <Route path="/configure" element={<CustomTablesPage />} />
        {/* Configure → Pricing: the org pricing-item/discount library (M1.10). */}
        <Route path="/configure/pricing" element={<PricingDefsPage />} />
        <Route path="/configure/operations" element={<OperationsPage />} />
        <Route path="/configure/rules" element={<RulesPage />} />
        {/* Configure → Interrogations: DFM thresholds + toggles (M4.7). */}
        <Route path="/configure/interrogations" element={<InterrogationsPage />} />
        {/* Settings → User Profile → Email Connection (M3.5). */}
        <Route path="/settings/email" element={<EmailConnectionPage />} />
        {/* Settings → Email Templates (M5.5). */}
        <Route path="/settings/email-templates" element={<EmailTemplatesPage />} />
        {/* Unknown paths redirect home rather than rendering the dashboard at a
            wrong URL (keeps the landing route distinct from the catch-all). */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
