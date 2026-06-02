#!/usr/bin/env bash
# schedule_linux.sh — register the 7 Insider agents with crontab.
#
# Appends 7 cron lines under a managed block. Idempotent: re-running
# strips the block and rewrites it.
#
# Logs land in ~/insider-routines/.state/logs/.

set -euo pipefail

ROOT="$HOME/insider-routines"
AGENTS="$ROOT/agents"
LOGS="$ROOT/.state/logs"
PY="$(command -v python3)"

if [[ -z "$PY" ]]; then
  echo "python3 not found on PATH. Install Python 3.10+ first." >&2
  exit 1
fi

mkdir -p "$LOGS"

MARK_START="# >>> insider-routines (managed by ZeroOne) >>>"
MARK_END="# <<< insider-routines (managed by ZeroOne) <<<"

# Pull current crontab, strip our managed block, append a fresh one.
current="$(crontab -l 2>/dev/null || true)"
stripped="$(printf '%s\n' "$current" | awk -v s="$MARK_START" -v e="$MARK_END" '
  $0==s {skip=1; next}
  $0==e {skip=0; next}
  !skip {print}
')"

run() {  # build one cron line: schedule cmd >> log 2>&1
  local schedule="$1" script="$2" name="$3"
  echo "${schedule} ${PY} ${AGENTS}/${script} >> ${LOGS}/${name}.cron.log 2>&1"
}

block="$(cat <<EOF
${MARK_START}
$(run "0 6 * * *"   "eddie.py"   "eddie")
$(run "0 19 * * 0"  "maggie.py"   "maggie")
$(run "0 8 * * 1"   "frank.py"  "frank")
$(run "0 */6 * * *" "maya.py"  "maya")
$(run "0 17 * * *"  "janet.py"   "janet")
$(run "*/30 * * * *" "sophie.py"  "sophie")
$(run "*/30 * * * *" "ross.py" "ross")
${MARK_END}
EOF
)"

# Reinstall.
printf '%s\n\n%s\n' "$stripped" "$block" | crontab -

echo "All 7 agents registered with crontab. Logs → $LOGS"
echo "Inspect: crontab -l"
echo "Uninstall: bash $ROOT/install/uninstall_linux.sh"
