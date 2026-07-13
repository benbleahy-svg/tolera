---
description: Build the current slice strictly test-first (red → green → refactor); mandatory for pricing/geometry math
argument-hint: "[what we're building, e.g. 'margin roll-up']"
allowed-tools: Bash(uv *), Bash(pytest *), Bash(ruff *), Read, Grep, Glob, Write, Edit
---
Build $ARGUMENTS strictly test-first. The fixture is the target.

Loop (repeat per behaviour, smallest slice first):
1. **Red.** Write ONE failing test that pins the next behaviour. For pricing/geometry: assert the exact golden figure from `/fixtures` (integer minor units + currency — never floats). Run it; confirm it fails **for the right reason**.
2. **Green.** Write the minimum code to pass. No speculative generality, no touching unrelated files.
3. **Refactor.** Clean up with the suite green. Run `uv run pytest -q -x` + ruff after.

Hard rules:
- Never write production code without a failing test first; never weaken a test to make it pass.
- Deterministic blocks get exact assertions. Never exact-match raw model output (Lens/AI quality goes through the eval suite, not unit tests).
- Tenancy tests: every new table/endpoint gets a cross-org denial test.
- If a test is hard to write, the design is wrong — stop and say so before contorting the test.
