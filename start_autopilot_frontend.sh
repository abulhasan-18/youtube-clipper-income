#!/bin/bash
# ==============================================================================
# Clipper AutoPilot - Option A: Simultaneous Concurrent Pipeline (Frontend Mode)
# - Producer Thread: Discovers & renders 9:16 Shorts with Hormozi captions in background
# - Uploader Thread: Simultaneously publishes each clip via visible Chrome on screen
# - Disk Space: Local .mp4 files deleted immediately after upload (keeps disk ~0 MB)
# - Target: 20 Viral Shorts / Day
# ==============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=========================================================================="
echo "🚀 Starting Clipper AutoPilot (Option A: Simultaneous Concurrent Pipeline)"
echo "   Mode: Frontend UI (Visible Chrome Browser on Screen)"
echo "   Target: 20 Shorts / Day | Producer & Uploader running in parallel"
echo "=========================================================================="

# Activate virtual environment if present
if [ -d "$DIR/.venv" ]; then
    source "$DIR/.venv/bin/activate"
fi

# Run with caffeinate to prevent Mac from sleeping while actively clipping and uploading
exec caffeinate -s -i "$DIR/.venv/bin/python3" autopilot.py --frontend
