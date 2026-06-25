/**
 * App layout: the persistent sidebar + the routed page content (`<Outlet/>`).
 * Rendered only for authenticated users (the auth gate lives at the app root).
 */

import { Outlet } from 'react-router-dom';

import { Sidebar } from './Sidebar';

export function AppShell({ onSignOut }: { onSignOut?: () => void }) {
  return (
    <div className="app-shell">
      <Sidebar onSignOut={onSignOut} />
      <main className="app-content">
        <Outlet />
      </main>
    </div>
  );
}
