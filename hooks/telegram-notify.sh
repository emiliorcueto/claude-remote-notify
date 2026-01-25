#!/bin/bash
# =============================================================================
# telegram-notify.sh - Claude Code Hook for Telegram Notifications (Multi-Session)
# =============================================================================
#
# Supports Telegram Topics (Forum Mode) for multiple Claude sessions.
# Each session posts to its own topic thread.
#
# Usage:
#   telegram-notify.sh [event-type] [--session NAME]
#
# Environment:
#   CLAUDE_SESSION - Session name (default: "default")
#
# =============================================================================

set -e

# -----------------------------------------------------------------------------
# Parse Arguments
# -----------------------------------------------------------------------------

EVENT_TYPE="notification"
SESSION_NAME="${CLAUDE_SESSION:-default}"

while [[ $# -gt 0 ]]; do
    case $1 in
        --session|-s)
            SESSION_NAME="$2"
            shift 2
            ;;
        *)
            EVENT_TYPE="$1"
            shift
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
SESSIONS_DIR="$CLAUDE_HOME/sessions"
CONFIG_FILE="$SESSIONS_DIR/$SESSION_NAME.conf"
GLOBAL_CONFIG="$CLAUDE_HOME/telegram-remote.conf"
NOTIFY_FLAG_FILE="$CLAUDE_HOME/notifications-enabled"
TMUX_SESSION="${TMUX_SESSION:-claude-$SESSION_NAME}"
CONTEXT_LINES=30

# -----------------------------------------------------------------------------
# Check if notifications are enabled
# -----------------------------------------------------------------------------

if [ ! -f "$NOTIFY_FLAG_FILE" ]; then
    exit 0
fi

# -----------------------------------------------------------------------------
# Load shared library and configuration
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LIB_DIR="${SCRIPT_DIR%/hooks}/lib"

# Source shared library if available
if [ -f "$LIB_DIR/common.sh" ]; then
    source "$LIB_DIR/common.sh"
    # Use safe config loading
    if ! load_session_config "$SESSION_NAME" "$CLAUDE_HOME" 2>/dev/null; then
        exit 0
    fi
else
    # Fallback to legacy loading if lib not available
    if [ -f "$CONFIG_FILE" ]; then
        source "$CONFIG_FILE"
    elif [ -f "$GLOBAL_CONFIG" ]; then
        source "$GLOBAL_CONFIG"
    else
        exit 0
    fi
fi

if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    exit 0
fi

# Topic ID is optional (for single-session setups)
TOPIC_ID="${TELEGRAM_TOPIC_ID:-}"

# -----------------------------------------------------------------------------
# Capture terminal context
# -----------------------------------------------------------------------------

get_terminal_context() {
    local session="${1:-$TMUX_SESSION}"
    
    if command -v tmux &> /dev/null && tmux has-session -t "$session" 2>/dev/null; then
        local context
        context=$(tmux capture-pane -t "$session" -p -S -"$CONTEXT_LINES" 2>/dev/null)
        echo "$context" | grep -v '^$' | tail -"$CONTEXT_LINES"
    else
        echo "[Terminal context not available]"
    fi
}

# -----------------------------------------------------------------------------
# Send notification
# -----------------------------------------------------------------------------

CONTEXT=$(get_terminal_context "$TMUX_SESSION")

# Determine emoji and header based on event type
case "$EVENT_TYPE" in
    "notification"|"permission"|"idle")
        EMOJI="🔔"
        HEADER="Awaiting Input"
        ;;
    "stop"|"complete")
        EMOJI="✅"
        HEADER="Task Complete"
        ;;
    "error")
        EMOJI="❌"
        HEADER="Error"
        ;;
    *)
        EMOJI="📢"
        HEADER="Alert"
        ;;
esac

# Build the message with session identifier
MESSAGE="$EMOJI [$SESSION_NAME] $HEADER

⏰ $(date '+%H:%M:%S')

━━━ Terminal Output ━━━
$CONTEXT
━━━━━━━━━━━━━━━━━━━━━━

💬 Reply here to send input"

# Build curl arguments
CURL_ARGS=(
    -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage"
    -d "chat_id=$TELEGRAM_CHAT_ID"
    --data-urlencode "text=$MESSAGE"
)

# Add topic ID if configured (for Forum groups)
if [ -n "$TOPIC_ID" ]; then
    CURL_ARGS+=(-d "message_thread_id=$TOPIC_ID")
fi

# Send to Telegram
curl "${CURL_ARGS[@]}" > /dev/null 2>&1

exit 0
