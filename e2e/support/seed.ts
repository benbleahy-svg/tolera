import type { APIRequestContext } from '@playwright/test';

// Reset the demo tenant to a known golden seed before a spec runs, so demos are deterministic.
// Backed by a TEST-ONLY endpoint the API exposes (seed framework, build block M0.5) — it MUST be
// disabled in production. `scenario` selects which fixture set to load (see docs/fixtures/).
export async function resetToSeed(
  request: APIRequestContext,
  scenario = 'fechner-baseline',
): Promise<void> {
  const apiURL = process.env.E2E_API_URL ?? 'http://localhost:8000';
  const res = await request.post(`${apiURL}/__test__/seed`, { data: { scenario } });
  if (!res.ok()) {
    throw new Error(`seed reset failed (${res.status()}): ${await res.text()}`);
  }
}
