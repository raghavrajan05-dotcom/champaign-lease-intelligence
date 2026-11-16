#!/usr/bin/env bash
# One-time setup (macOS): run the Green Street scrape automatically every day.
#
# Uses launchd, the Mac's own scheduler. Unlike cron, if the laptop is asleep at a
# scheduled time the job runs when it wakes. It is scheduled several times a day and
# at login, but the scrape script stops early once today's file is published, so
# Green Street's site is still read at most once per day.
#
# Usage (from the project folder):  bash scripts/install_greenstreet_schedule.sh
# Undo:                             bash scripts/install_greenstreet_schedule.sh remove
set -euo pipefail
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.champaignlease.greenstreet"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/champaign-lease-greenstreet.log"
TARGET="gui/$(id -u)"

# Stop any earlier copy of the job, and drop the old cron line that this replaces.
launchctl bootout "$TARGET/$LABEL" 2>/dev/null || true
if crontab -l 2>/dev/null | grep -q scrape_greenstreet_local; then
  crontab -l | grep -v scrape_greenstreet_local | crontab - || true
  echo "Removed the old cron entry."
fi

if [ "${1:-}" = "remove" ]; then
  rm -f "$PLIST"
  echo "Schedule removed."
  exit 0
fi

mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
times=""
for hour in 9 12 15 18 21; do
  times+="    <dict><key>Hour</key><integer>$hour</integer><key>Minute</key><integer>7</integer></dict>
"
done
cat > "$PLIST" <<PLIST_END
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$PROJECT/scripts/scrape_greenstreet_local.sh</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJECT</string>
  <key>RunAtLoad</key><true/>
  <key>StartCalendarInterval</key>
  <array>
$times  </array>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST_END

launchctl bootstrap "$TARGET" "$PLIST"
echo "Installed. It runs now, at login, and at 9:07, 12:07, 15:07, 18:07 and 21:07"
echo "(or when the laptop next wakes). To see what it did:"
echo "  tail -20 \"$LOG\""
