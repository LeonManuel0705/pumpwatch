#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
label="com.leon.pumpwatch-watchdog"
plist="$HOME/Library/LaunchAgents/$label.plist"
python="$(command -v python3)"

cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$label</string>
    <key>ProgramArguments</key>
    <array>
        <string>$python</string>
        <string>$root/scripts/watchdog.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$root</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>17</integer></dict>
        <dict><key>Hour</key><integer>21</integer><key>Minute</key><integer>17</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/pumpwatch-watchdog.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/pumpwatch-watchdog.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$plist"
echo "watchdog installed, it checks twice a day and on the next wake after a missed slot"
