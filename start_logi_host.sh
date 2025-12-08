#!/bin/bash
# Start the MX Creative host on macOS (auto-detects Dialpad + Keypad)
# Usage: ./start_logi_host.sh [receiver_ip]
#   e.g. ./start_logi_host.sh 10.10.101.133

cd "$(dirname "$0")"

# Unload Logitech Options+ launch agents to prevent auto-restart
echo "[*] Disabling Logitech Options+ (required for HID access)..."
launchctl unload /Library/LaunchAgents/com.logi.optionsplus.plist 2>/dev/null
launchctl unload ~/Library/LaunchAgents/com.logi.optionsplus.plist 2>/dev/null
launchctl unload /Library/LaunchAgents/com.logitech.manager.daemon.plist 2>/dev/null
launchctl unload ~/Library/LaunchAgents/com.logitech.manager.daemon.plist 2>/dev/null

# Kill any remaining processes
killall logioptionsplus_agent LogiPluginService LogiPluginServiceExt LogiPluginServiceNative logi_options_plus 2>/dev/null
sleep 1

echo "[*] Logitech Options+ disabled. To re-enable, run:"
echo "    launchctl load /Library/LaunchAgents/com.logi.optionsplus.plist"

if [ -n "$1" ]; then
    DYLD_LIBRARY_PATH=/opt/homebrew/lib ./venv/bin/python host.py --host="$1"
else
    DYLD_LIBRARY_PATH=/opt/homebrew/lib ./venv/bin/python host.py
fi
