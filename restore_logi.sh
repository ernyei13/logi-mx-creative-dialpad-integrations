#!/bin/bash
# Re-enable Logitech Options+ after using the HID host
# Usage: ./restore_logi.sh

echo "[*] Re-enabling Logitech Options+..."
launchctl load /Library/LaunchAgents/com.logi.optionsplus.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.logi.optionsplus.plist 2>/dev/null
launchctl load /Library/LaunchAgents/com.logitech.manager.daemon.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.logitech.manager.daemon.plist 2>/dev/null

echo "[*] Done. Logitech Options+ should restart automatically."
