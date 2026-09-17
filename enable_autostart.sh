#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PLIST_NAME="com.clipper.autopilot.plist"
TARGET="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "Configuring 24/7 Auto-Start on Boot (macOS LaunchAgent)..."

# Unload existing if loaded
launchctl unload -w "$TARGET" 2>/dev/null

# Copy plist to LaunchAgents
mkdir -p "$HOME/Library/LaunchAgents"
cp "$DIR/$PLIST_NAME" "$TARGET"

# Load into launchd
launchctl load -w "$TARGET"

echo "✓ Auto-start enabled successfully!"
echo "AutoPilot will now automatically start whenever your computer turns on or logs in."
echo ""
echo "Helpful commands:"
echo "  View live logs: tail -f \"$DIR/autopilot.log\""
echo "  Disable auto-start: ./disable_autostart.sh"
