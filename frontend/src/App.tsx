/**
 * Routes. Each primary-nav destination renders inside the persistent `AppShell`;
 * the destination screens themselves arrive in later blocks (placeholder for
 * now). Sign-out is wired here (the only Clerk touch-point below the auth gate)
 * and handed to the shell.
 */

import { useClerk } from '@clerk/clerk-react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { PlaceholderPage } from './pages/PlaceholderPage';
import { AppShell } from './shell/AppShell';
import { NAV_ITEMS } from './shell/nav';

export default function App() {
  const { signOut } = useClerk();

  return (
    <Routes>
      <Route element={<AppShell onSignOut={() => void signOut()} />}>
        {NAV_ITEMS.map(({ to, labelKey }) => (
          <Route key={to} path={to} element={<PlaceholderPage titleKey={labelKey} />} />
        ))}
        {/* Unknown paths redirect home rather than rendering the dashboard at a
            wrong URL (keeps the landing route distinct from the catch-all). */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
