import { clerkSetup } from '@clerk/testing/playwright';
import { test as setup } from '@playwright/test';

// Global setup: mints a Clerk Testing Token (needs CLERK_SECRET_KEY + CLERK_PUBLISHABLE_KEY)
// so specs can sign in without hitting bot detection.
// Until the team adds the dev Clerk keys, this skips cleanly and the (fixme) demos stay green in CI.
setup('clerk global setup', async () => {
  setup.skip(!process.env.CLERK_SECRET_KEY, 'No CLERK_SECRET_KEY yet — demos are still fixme.');
  await clerkSetup();
});
