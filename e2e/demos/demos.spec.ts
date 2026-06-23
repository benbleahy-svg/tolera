import { test } from '../support/fixtures';
import { DEMOS } from './demo-registry';

// One placeholder per acceptance demo. Each is `fixme` until its milestone lands; promote it then
// (remove `.fixme`, add the real click-through + assertion vs the fixture). The Playwright report
// then becomes a live "N / 14 demos automated" scoreboard — and M6.10 (all green) is the pilot's
// definition of done. See demo-e-markups.spec.ts for the worked template.

for (const demo of DEMOS) {
  test.fixme(
    `Demo ${demo.id} · ${demo.title}  [first replayable: ${demo.firstReplayable}]`,
    async ({ authedPage }) => {
      // To promote this demo when its milestone is built:
      //   1. delete `.fixme`
      //   2. resetToSeed(request, '<scenario>')   // deterministic start
      //   3. drive the flow per docs/reference/screenshots/Demo<ID>/   (the UI ground truth)
      //   4. assert against the fixture in docs/fixtures/  (see DEMOS-TRACEABILITY.md → Demo <ID>)
      void authedPage;
    },
  );
}
