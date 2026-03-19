#!/usr/bin/env bash
# =============================================================================
# cleanup-old-listeners.sh - Remove old single-session listener processes
# =============================================================================
#
# Finds and kills old single-session listener processes (telegram-listener.py
# --session) that conflict with the multi-session listener. Also cleans up
# stale PID files.
#
# Usage:
#   cleanup-old-listeners.sh
#
# The multi-session listener calls this script interactively when it detects
# old single-session listeners at startup.
# =============================================================================

set -euo pipefail

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
PIDS_DIR="$CLAUDE_HOME/pids"

killed=0
cleaned=0

echo "Scanning for old single-session listeners..."

# Kill running single-session listener processes
if [[ -d "$PIDS_DIR" ]]; then
    for pid_file in "$PIDS_DIR"/listener-*.pid; do
        [[ -f "$pid_file" ]] || continue

        basename="$(basename "$pid_file")"

        # Skip the multi-session PID file
        if [[ "$basename" == "listener-multi.pid" ]]; then
            continue
        fi

        session_name="${basename#listener-}"
        session_name="${session_name%.pid}"

        pid="$(cat "$pid_file" 2>/dev/null)" || continue
        if [[ -z "$pid" ]]; then
            rm -f "$pid_file"
            ((cleaned++)) || true
            continue
        fi

        if kill -0 "$pid" 2>/dev/null; then
            echo "  Killing $session_name listener (PID: $pid)"
            kill "$pid" 2>/dev/null || true
            ((killed++)) || true
        fi

        rm -f "$pid_file"
        ((cleaned++)) || true
    done
fi

echo ""
if [[ $killed -gt 0 ]] || [[ $cleaned -gt 0 ]]; then
    echo "Cleanup complete: $killed process(es) killed, $cleaned PID file(s) removed"
else
    echo "No old listeners found"
fi
