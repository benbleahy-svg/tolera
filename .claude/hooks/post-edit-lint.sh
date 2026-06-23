#!/usr/bin/env bash
# PostToolUse[Edit|Write] — lint the file just edited for fast feedback.
# Non-blocking by nature (the edit already ran); exit 2 only surfaces the report to Claude.
# Stays silent until ruff is actually installed (pre-M0.1) — never blocks on "ruff missing".
set -uo pipefail

input="$(cat)"
file="$(printf '%s' "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null || true)"
[ -n "$file" ] || exit 0
case "$file" in *.py) ;; *) exit 0 ;; esac
[ -f "$file" ] || exit 0

# Resolve a ruff that really runs (PATH first; else uv, but only if ruff is in the env).
if command -v ruff >/dev/null 2>&1; then
  RUFF=(ruff)
elif command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ] && uv run ruff --version >/dev/null 2>&1; then
  RUFF=(uv run ruff)
else
  exit 0
fi

out="$("${RUFF[@]}" check "$file" 2>&1)"; status=$?
if [ "$status" -ne 0 ] && [ -n "$out" ]; then
  printf 'ruff found issues in %s:\n%s\n' "$file" "$out" >&2
  exit 2
fi
exit 0
