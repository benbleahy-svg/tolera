#!/usr/bin/env bash
# Stop hook — enforce "green or it's not done". When Python files changed since HEAD, run ruff +
# a quick pytest and block the turn from ending if they fail (Claude then keeps fixing).
# Bypass: export CLAUDE_SKIP_TEST_GATE=1. Inert until the Python project exists (pre-M0.1);
# never blocks merely because a tool isn't installed.
set -uo pipefail

[ "${CLAUDE_SKIP_TEST_GATE:-0}" = "1" ] && exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
[ -f pyproject.toml ] || exit 0

changed="$( { git diff --name-only -- '*.py'; git diff --cached --name-only -- '*.py'; git ls-files --others --exclude-standard -- '*.py'; } 2>/dev/null )"
[ -n "$changed" ] || exit 0

fail() { printf 'Stop gate: %s\n' "$1" >&2; exit 2; }

# Resolve ruff / pytest only if they genuinely run.
RUFF=(); PYTEST=()
if command -v ruff >/dev/null 2>&1; then RUFF=(ruff)
elif command -v uv >/dev/null 2>&1 && uv run ruff --version >/dev/null 2>&1; then RUFF=(uv run ruff); fi
if command -v pytest >/dev/null 2>&1; then PYTEST=(pytest)
elif command -v uv >/dev/null 2>&1 && uv run pytest --version >/dev/null 2>&1; then PYTEST=(uv run pytest); fi

# 1) ruff (fast) — block on lint failures.
if [ ${#RUFF[@]} -gt 0 ]; then
  out="$("${RUFF[@]}" check . 2>&1)" || fail "ruff failed — fix lint before finishing:
$out"
fi

# 2) pytest (quick, stop at first failure). Skip if no tests dir. Exit 5 = "no tests collected" = OK.
if [ ${#PYTEST[@]} -gt 0 ] && [ -d tests ]; then
  out="$("${PYTEST[@]}" -q -x 2>&1)"; status=$?
  if [ "$status" -ne 0 ] && [ "$status" -ne 5 ]; then
    fail "tests are red — fix before finishing (bypass: CLAUDE_SKIP_TEST_GATE=1):
$out"
  fi
fi
exit 0
