import { test, expect } from '../support/fixtures';
import { resetToSeed } from '../support/seed';

// Demo E — Custom Markups & Margins · first replayable at M1 (the M1.13 golden harness).
// Narrative: spec #acceptance + #kalk + #costing  ·  UI truth: docs/reference/screenshots/DemoE/
// Proof: reproduces the six worked examples; the headline is the Difficult-Material total
// (golden 2160.84, rendered de-DE as "2.160,84 €" — confirm the currency against the fixture
// per the DACH delta: the product is EUR/CHF even though the PP source example was in $).
//
// THIS IS THE TEMPLATE the other demos copy. It is `fixme` until M1 ships the pricing UI;
// then remove `.fixme`, fill the steps from the DemoE/ screenshots, and it gates every PR after.

test.fixme('Demo E · Example 6 — Difficult Material reproduces the golden total', async ({ authedPage, request }) => {
  // 1. Deterministic start — load the seeded Demo E quote.
  await resetToSeed(request, 'demoE-markups');

  // 2. Open the seeded demo quote (screenshot: DemoE/demo-quote).
  await authedPage.goto('/quotes/demo-e');

  // 3. Follow the #acceptance Demo E script — add the custom pricing item (Calc Type + cost
  //    category + colour), apply the markup to that category only, enter Example 6's inputs.
  //    Build to the DemoE/ screenshots; do not restate the narrative here. For example:
  // await authedPage.getByRole('button', { name: 'Neuer Preisposten' }).click();
  // await authedPage.getByLabel('Kostenkategorie').selectOption('Material');
  // await authedPage.getByLabel('Aufschlag %').fill('15');

  // 4. Assert the grand total equals the M1.13 golden figure, formatted de-DE.
  //    Prefer a stable data-testid over text/position — ask the frontend block to add it.
  await expect(authedPage.getByTestId('quote-grand-total')).toHaveText('2.160,84 €');
});
