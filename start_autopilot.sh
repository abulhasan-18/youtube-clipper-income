#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

PID_FILE="autopilot.pid"
LOG_FILE="autopilot.log"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "AutoPilot is already running (PID: $PID)."
        echo "To view live logs: tail -f $LOG_FILE"
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

echo "Starting Autonomous Clipper & Publisher (24/7 Loop)..."
# Use caffeinate to keep the Mac awake for background processing (even when screen turns off)
nohup caffeinate -s -i "$DIR/.venv/bin/python3" "$DIR/cli.py" autopilot >> "$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"

echo "✓ AutoPilot is now running in the background (PID: $PID)!"
echo "It will continuously discover, clip, and upload Shorts every 15 minutes 24/7."
echo ""
echo "Helpful commands:"
echo "  View live logs: tail -f $LOG_FILE"
echo "  Stop AutoPilot: ./stop_autopilot.sh"
