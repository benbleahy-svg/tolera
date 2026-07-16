# BLOCKED — M3.8 (Review-item generator + lifecycle + Create Rule UI + SET ALL)

**Session ended:** 2026-07-16 · **Branch:** `feature/m3.8-review-items` · **Nothing built** (halt fired during the self-grill, before any code).

## What is needed from a human

**One decision:** how to stop a rule's `regex` operator from hanging a Celery worker when it runs org-authored patterns over customer-supplied print text.

This is the `[2026-07-16] OPEN:` entry *"M3.7/M3.8 — ReDoS exposure from org-authored rule regexes over customer print text"* in `docs/decisions/DECISIONS.md`. M3.7 shipped the evaluator as a pure, unwired module and explicitly deferred the fix: **"must be resolved before M3.8 wires it."** M3.8 is exactly that wiring — the block whose job is to execute rules from the post-AI trigger — so it cannot proceed around this.

## Why this is a halt and not a default

CLAUDE.md §6.1 puts **security** in the do-not-guess set. Both live options change more than a line:

- **(a) Bound the match** — Python's `re` cannot be timed out from a thread (the SRE engine holds the GIL in C and never checks for interrupts; `signal.alarm` and thread-based decorators fail the same way — CPython #67878, bpo-24555). Real mitigation means **adding the `regex` module** (a C-extension dependency on a security path — it is *not* in `pyproject.toml` today) **or a killable subprocess per match** (new failure mode + per-evaluation cost on every Celery rule run).
- **(b) Reject risky patterns at import** — no dependency, fails closed at config time with a clear message, but heuristic and incomplete; it also changes M3.6's import contract and therefore what the M3.8 Create Rule UI must render as an error state.

A new dependency vs. a subprocess architecture, on the path that touches customer print content, is a human call.

## Evidence (measured this session, on the real code path)

Reproduced through the shipped `app.rules_eval._compare_string` — pattern `^(a+)+$` against a non-matching `'a'*n + '!'`:

| input | time |
|---|---|
| 22 chars | 0.12 s |
| 24 chars | 0.48 s |
| 26 chars | 1.94 s |
| 28 chars | 7.79 s |

Doubling per character, matching the figures in the DECISIONS entry. **No malicious admin is required:** a shop authors an innocent backtracking pattern (`(\d+[ -]?)+` is easy to write by accident), then a *customer* uploads the print whose text layer triggers it.

## Recommended default (from the DECISIONS entry — still the right call)

**(a) + (b)**: bound the match *and* reject the obvious nested-quantifier shapes at import. Option (c) (cap the scanned text length) is ineffective — the blow-up is at 24–30 characters. Option (d) (accept the risk) leaves a customer-triggerable worker hang.

If you want the smallest change that unblocks: **add `regex` to `pyproject.toml` and run rule patterns under `regex.search(..., timeout=…)`**, plus a nested-quantifier reject at M3.6 import.

## Credentials / dependencies

None missing. All of M3.8's dependencies are merged: M3.7 (#45), M3.2 (#39), M1.7 (#16).

## To resume

1. Record the decision in `docs/decisions/DECISIONS.md` (move the `OPEN:` entry to a dated resolved entry).
2. Delete this file.
3. Re-run `/block M3.8` in a fresh session.
