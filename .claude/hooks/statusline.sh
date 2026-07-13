#!/usr/bin/env bash
# Statusline — branch + context usage, with a loud handoff cue.
# The context % is the handoff trigger: >70% = plan to finish the current
# red->green loop and /handoff at a green boundary; >85% = hand off NOW.
set -uo pipefail
input="$(cat)"
python3 - "$input" <<'PY'
import json,subprocess,sys
d=json.loads(sys.argv[1]) if len(sys.argv)>1 and sys.argv[1] else {}
model=(d.get("model") or {}).get("display_name","")
cw=d.get("context_window") or {}
pct=cw.get("used_percentage")
if pct is None:
    try:
        u=(d.get("current_usage") or {})
        used=sum(u.get(k,0) for k in ("input_tokens","cache_creation_input_tokens","cache_read_input_tokens"))
        size=cw.get("context_window_size") or 200000
        pct=round(100*used/size) if used else None
    except Exception: pct=None
try:
    branch=subprocess.run(["git","branch","--show-current"],capture_output=True,text=True,timeout=2).stdout.strip()
except Exception: branch=""
parts=[p for p in (model, f"⎇ {branch}" if branch else "") if p]
if isinstance(pct,(int,float)):
    pct=round(pct)
    if pct>=85: parts.append(f"ctx {pct}% ⛔ /handoff NOW")
    elif pct>=70: parts.append(f"ctx {pct}% ⚠ green boundary → /handoff")
    else: parts.append(f"ctx {pct}%")
print(" · ".join(parts))
PY
exit 0
