#!/usr/bin/env bash
# context-kit 30-second demo
#
# Three commands. Shows the loop:
#   orient     — "this repo knows what it is and where to start"
#   inventory  — "this repo knows what exists right now"
#   hotpath    — "this repo knows where the bloat / drift may happen"
#
# Run from the repo root. Requires Python 3.9+. No other deps.
#
# To record:  asciinema rec demo.cast -c "examples/demo.sh"
# To replay:  asciinema play demo.cast

set -euo pipefail

CKIT="python3 context_kit.py"

heading() {
  printf "\n\033[1m== %s ==\033[0m\n\n" "$1"
}

pause() {
  # Tiny pause so a viewer can read each section. Keep total under 30s.
  sleep "${DEMO_PAUSE:-1.2}"
}

heading "1/3  context-kit orient   (this repo knows what it is)"
$CKIT orient | head -40
pause

heading "2/3  context-kit inventory --check   (this repo knows what exists)"
if $CKIT inventory --check; then
  printf "  -> inventory is current. CI would pass on this commit.\n"
else
  printf "  -> inventory is stale. Developer fix:  %s inventory --write\n" "$CKIT"
fi
pause

heading "3/3  context-kit hotpath   (this repo knows where the bloat may be)"
$CKIT hotpath | tail -20
pause

heading "Result"
cat <<'EOF'
This repo knows:
  - what it is              (narrative anchor + start-here)
  - what exists right now   (inventory --check passes; --json is machine-readable)
  - where bloat may grow    (hot-path summary, with thresholds)

That's the whole pattern. Same three commands work in any project that
ran `context-kit init` — the bundled Claude skill calls them at the
start of every session.

  $ pip install contextkit-ai
  $ context-kit init "My App"
EOF
