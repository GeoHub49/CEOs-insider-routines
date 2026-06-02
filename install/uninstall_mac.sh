#!/usr/bin/env bash
# uninstall_mac.sh — remove all Insider launchd agents.
set -euo pipefail
LA_DIR="$HOME/Library/LaunchAgents"
for name in eddie maggie frank maya janet sophie ross; do
  plist="$LA_DIR/ventures.jackson.insider.${name}.plist"
  [[ -f "$plist" ]] || continue
  launchctl unload "$plist" 2>/dev/null || true
  rm -f "$plist"
  echo "  - removed ventures.jackson.insider.${name}"
done
echo "All Insider agents unregistered. Your scripts + state remain at ~/insider-routines/."
