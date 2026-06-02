#!/usr/bin/env bash
# schedule_mac.sh — register the 7 Insider agents with macOS launchd.
#
# Writes 7 .plist files to ~/Library/LaunchAgents/ and loads them.
# Idempotent: re-running unloads + reloads cleanly.
#
# Logs land in ~/insider-routines/.state/logs/.

set -euo pipefail

ROOT="$HOME/insider-routines"
AGENTS="$ROOT/agents"
LOGS="$ROOT/.state/logs"
LA_DIR="$HOME/Library/LaunchAgents"
PY="$(command -v python3)"

if [[ -z "$PY" ]]; then
  echo "python3 not found on PATH. Install Python 3.10+ first." >&2
  exit 1
fi

mkdir -p "$LA_DIR" "$LOGS"

write_plist() {
  local name="$1"
  local script="$2"
  shift 2
  local schedule_xml="$*"

  local label="ventures.jackson.insider.${name}"
  local plist="$LA_DIR/${label}.plist"

  cat >"$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PY}</string>
    <string>${AGENTS}/${script}</string>
  </array>
  <key>WorkingDirectory</key><string>${ROOT}</string>
  <key>StandardOutPath</key><string>${LOGS}/${name}.out.log</string>
  <key>StandardErrorPath</key><string>${LOGS}/${name}.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  ${schedule_xml}
</dict>
</plist>
EOF

  # Unload silently if previously loaded, then load fresh.
  launchctl unload "$plist" 2>/dev/null || true
  launchctl load "$plist"
  echo "  ✓ ${label}"
}

# ── Schedule helpers ─────────────────────────────────────────────────────────

at_hm() {  # daily at HH:MM
  local hour="$1" minute="$2"
  cat <<EOF
<key>StartCalendarInterval</key>
<dict>
  <key>Hour</key><integer>${hour}</integer>
  <key>Minute</key><integer>${minute}</integer>
</dict>
EOF
}

weekly_at() {  # weekday (0=Sun, 1=Mon, ...) at HH:MM
  local weekday="$1" hour="$2" minute="$3"
  cat <<EOF
<key>StartCalendarInterval</key>
<dict>
  <key>Weekday</key><integer>${weekday}</integer>
  <key>Hour</key><integer>${hour}</integer>
  <key>Minute</key><integer>${minute}</integer>
</dict>
EOF
}

every_seconds() {  # interval in seconds
  cat <<EOF
<key>StartInterval</key><integer>$1</integer>
EOF
}

# ── Register all 7 ───────────────────────────────────────────────────────────

echo "Registering Insider agents with launchd…"
write_plist "eddie"   "eddie.py"   "$(at_hm 6 0)"
write_plist "maggie"   "maggie.py"   "$(weekly_at 0 19 0)"   # Sunday 19:00
write_plist "frank"  "frank.py"  "$(weekly_at 1 8 0)"    # Monday  08:00
write_plist "maya"  "maya.py"  "$(every_seconds 21600)" # every 6h
write_plist "janet"   "janet.py"   "$(at_hm 17 0)"
write_plist "sophie"  "sophie.py"  "$(every_seconds 1800)"  # every 30m
write_plist "ross" "ross.py" "$(every_seconds 1800)"  # every 30m

echo
echo "All 7 agents registered. Logs → $LOGS"
echo "Unregister anytime with: bash $ROOT/install/uninstall_mac.sh"
