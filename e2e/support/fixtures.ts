import { test as base, expect, type Page } from '@playwright/test';
import { signInAsPilot } from './auth';

// Custom fixtures shared by every demo spec.
//   authedPage — a page already signed in as the seeded Fechner pilot user.
type Fixtures = {
  authedPage: Page;
};

export const test = base.extend<Fixtures>({
  authedPage: async ({ page }, use) => {
    await signInAsPilot(page);
    await use(page);
  },
});

export { expect };
