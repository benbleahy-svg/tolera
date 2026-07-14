#!/usr/bin/env bash
# Stop hook — enforce "green or it's not done". When Python files changed since HEAD, run ruff +
# pytest and block the turn from ending if they fail (Claude then keeps fixing). When frontend
# files changed, run oxlint + the vitest tests whose import graph touches them (M2.6 addition —
# the M2.4 merge damage shipped through the Python-only gate).
# SCOPED for speed: ruff checks only the changed files; pytest runs only the tests that plausibly
# cover them (changed test files + tests/test_<stem>*.py per changed app module). If no matching
# tests are found, it falls back to the full quick suite. The FULL suite still gates /ship and CI.
# Bypass: export CLAUDE_SKIP_TEST_GATE=1. Inert until the Python project exists (pre-M0.1);
# never blocks merely because a tool isn't installed.
set -uo pipefail

[ "${CLAUDE_SKIP_TEST_GATE:-0}" = "1" ] && exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

fail() { printf 'Stop gate: %s\n' "$1" >&2; exit 2; }

# ---------------------------------------------------------------- frontend
# Gate changed frontend sources: oxlint on the .ts/.tsx among them, then
# `vitest related` so a broken shared import (i18n JSON, a page component)
# reddens every test that transitively loads it. Inert without node_modules.
if [ -f frontend/package.json ] && [ -d frontend/node_modules ]; then
  fe_changed="$( { git diff --name-only -- 'frontend/src'; git diff --cached --name-only -- 'frontend/src'; git ls-files --others --exclude-standard -- 'frontend/src'; } 2>/dev/null | sort -u )"
  fe_existing=()
  while IFS= read -r f; do [ -n "$f" ] && [ -f "$f" ] && fe_existing+=("${f#frontend/}"); done <<< "$fe_changed"
  if [ ${#fe_existing[@]} -gt 0 ]; then
    fe_lintable=()
    for f in "${fe_existing[@]}"; do case "$f" in *.ts|*.tsx) fe_lintable+=("$f") ;; esac; done
    if [ ${#fe_lintable[@]} -gt 0 ]; then
      out="$(cd frontend && npx oxlint "${fe_lintable[@]}" 2>&1)" \
        || fail "oxlint failed — fix lint before finishing:
$out"
    fi
    out="$(cd frontend && npx vitest related --run --passWithNoTests "${fe_existing[@]}" 2>&1)" \
      || fail "frontend tests are red [vitest related, ${#fe_existing[@]} changed file(s)] — fix before finishing (bypass: CLAUDE_SKIP_TEST_GATE=1):
$out"
  fi
fi

# ---------------------------------------------------------------- backend
[ -f pyproject.toml ] || exit 0

changed="$( { git diff --name-only -- '*.py'; git diff --cached --name-only -- '*.py'; git ls-files --others --exclude-standard -- '*.py'; } 2>/dev/null | sort -u )"
[ -n "$changed" ] || exit 0

# Only files that still exist (a deleted file can't be linted).
existing=()
while IFS= read -r f; do [ -f "$f" ] && existing+=("$f"); done <<< "$changed"
[ ${#existing[@]} -gt 0 ] || exit 0

# Resolve ruff / pytest only if they genuinely run. Prefer the project's own
# environment (the uv-managed .venv, then `uv run`) over a bare tool on PATH:
# a stray global pytest/ruff (wrong Python, missing project deps) would otherwise
# shadow the pinned interpreter and fail to even import the app — a false red.
RUFF=(); PYTEST=()
if [ -x .venv/bin/ruff ]; then RUFF=(.venv/bin/ruff)
elif command -v uv >/dev/null 2>&1 && uv run ruff --version >/dev/null 2>&1; then RUFF=(uv run ruff)
elif command -v ruff >/dev/null 2>&1; then RUFF=(ruff); fi
if [ -x .venv/bin/pytest ]; then PYTEST=(.venv/bin/pytest)
elif command -v uv >/dev/null 2>&1 && uv run pytest --version >/dev/null 2>&1; then PYTEST=(uv run pytest)
elif command -v pytest >/dev/null 2>&1; then PYTEST=(pytest); fi

# 1) ruff (fast) — changed files only; block on lint failures.
if [ ${#RUFF[@]} -gt 0 ]; then
  out="$("${RUFF[@]}" check "${existing[@]}" 2>&1)" || fail "ruff failed — fix lint before finishing:
$out"
fi

# 2) pytest — scoped to the tests covering the changed files; fall back to the full
#    quick suite when nothing matches. Exit 5 = "no tests collected" = OK.
if [ ${#PYTEST[@]} -gt 0 ] && [ -d tests ]; then
  targets=()
  for f in "${existing[@]}"; do
    case "$f" in
      tests/*) targets+=("$f") ;;
      *)
        stem="$(basename "$f" .py)"
        while IFS= read -r t; do targets+=("$t"); done \
          < <(find tests -name "test_*${stem}*.py" -o -name "test_${stem}.py" 2>/dev/null)
        ;;
    esac
  done
  # De-duplicate.
  if [ ${#targets[@]} -gt 0 ]; then
    mapfile -t targets < <(printf '%s\n' "${targets[@]}" | sort -u)
    out="$("${PYTEST[@]}" -q -x "${targets[@]}" 2>&1)"; status=$?
    scope="scoped tests (${#targets[@]} file(s))"
  else
    out="$("${PYTEST[@]}" -q -x 2>&1)"; status=$?
    scope="full quick suite (no matching scoped tests)"
  fi
  if [ "$status" -ne 0 ] && [ "$status" -ne 5 ]; then
    fail "tests are red [$scope] — fix before finishing (bypass: CLAUDE_SKIP_TEST_GATE=1):
$out"
  fi
fi
exit 0
