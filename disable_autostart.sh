#!/bin/bash
PLIST_NAME="com.clipper.autopilot.plist"
TARGET="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "Disabling AutoPilot auto-start on boot..."
launchctl unload -w "$TARGET" 2>/dev/null
rm -f "$TARGET"
echo "✓ Auto-start disabled."
