---
description: Interrogate me on the current block's scope and edge cases before any code is written
argument-hint: "[optional focus, e.g. 'tax rounding', 'schema']"
allowed-tools: Read, Grep, Glob
---
With the current block's sources loaded (its spec anchors, folded sub-spec, KB links — load them first if not already), **grill me** before we write any code. $ARGUMENTS

Rules of the grill:
- Ask one question at a time; drill into vague answers instead of moving on.
- Prioritise what is **expensive to reverse**: schema, money/tax math, tenancy/authz, API contracts, state machines.
- Probe edge cases the spec is silent on: empty/zero/negative quantities, currency + rounding, cross-org access, concurrent edits, retries/idempotency, German vs English strings.
- Challenge scope: what is explicitly OUT of this block? Where is the line to the next block?
- When an answer contradicts a source, say so and cite the source (precedence: DECISIONS.md > spec > folded sub-spec > KB; DACH delta overrides).
- Anything still ambiguous and expensive to reverse at the end → candidate `OPEN:` for `docs/decisions/DECISIONS.md` — never guess it.

Finish with: (1) the agreed scope in ≤5 bullets, (2) the acceptance check restated, (3) the `OPEN:` candidates. Then STOP and wait for my go-ahead to build test-first.
