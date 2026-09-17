#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

PID_FILE="autopilot.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping AutoPilot (PID: $PID)..."
        kill "$PID"
        rm -f "$PID_FILE"
        echo "✓ AutoPilot stopped successfully."
        exit 0
    fi
fi

echo "AutoPilot is not currently running."
rm -f "$PID_FILE"
