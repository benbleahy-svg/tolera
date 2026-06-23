import { clerk, setupClerkTestingToken } from '@clerk/testing/playwright';
import type { Page } from '@playwright/test';

// Sign in as the seeded Fechner pilot user. `clerk.signIn` internally calls
// setupClerkTestingToken; we call it explicitly too so any pre-sign-in navigation is covered.
export async function signInAsPilot(page: Page): Promise<void> {
  await setupClerkTestingToken({ page });
  await page.goto('/'); // load the app so Clerk's client initializes before signIn
  await clerk.signIn({
    page,
    signInParams: {
      strategy: 'password',
      identifier: requireEnv('E2E_USER_EMAIL'),
      password: requireEnv('E2E_USER_PASSWORD'),
    },
  });
}

function requireEnv(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`Missing env ${name} — copy e2e/.env.example to e2e/.env and fill it.`);
  return v;
}
