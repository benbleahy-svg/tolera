import { defineConfig, devices } from '@playwright/test';

// The app under test. Override per environment with E2E_BASE_URL.
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:5173';

export default defineConfig({
  testDir: '.',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['html', { open: 'never' }], ['list']],
  use: {
    baseURL,
    // DACH defaults — the product is German-first, metric, EUR/CHF.
    locale: 'de-DE',
    timezoneId: 'Europe/Berlin',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    // Runs once: exchanges CLERK_SECRET_KEY for a Testing Token used by all specs.
    { name: 'setup', testMatch: /global\.setup\.ts$/ },
    {
      name: 'chromium',
      testMatch: /demos\/.*\.spec\.ts$/,
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
    },
  ],

  // Boot the app for E2E. UNCOMMENT once M0.1/M1 can serve the frontend + API,
  // and adjust the commands to match the real run scripts.
  // webServer: [
  //   { command: 'uv run uvicorn app.main:app --port 8000', cwd: '..', url: 'http://localhost:8000/health', reuseExistingServer: !process.env.CI, timeout: 120_000 },
  //   { command: 'npm --prefix ../frontend run dev', url: baseURL, reuseExistingServer: !process.env.CI, timeout: 120_000 },
  // ],
});
