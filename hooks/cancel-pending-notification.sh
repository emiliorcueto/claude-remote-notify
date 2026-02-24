#!/bin/bash
# =============================================================================
# cancel-pending-notification.sh - Cancel pending delayed Telegram notification
# =============================================================================
#
# Called when user provides input before debounce timer expires.
# Sources lib/common.sh and delegates to cancel_pending_notification().
#
# Usage:
#   cancel-pending-notification.sh [--session NAME]
#
# Environment:
#   CLAUDE_SESSION - Fallback session name (default: "default")
#
# =============================================================================

set -euo pipefail

SESSION_NAME="${CLAUDE_SESSION:-default}"

while [[ $# -gt 0 ]]; do
    case $1 in
        --session|-s)
            SESSION_NAME="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LIB_DIR="${SCRIPT_DIR%/hooks}/lib"

if [ -f "$LIB_DIR/common.sh" ]; then
    source "$LIB_DIR/common.sh"
else
    echo "Error: lib/common.sh not found" >&2
    exit 1
fi

cancel_pending_notification "$SESSION_NAME"
