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
CONTEXT_LINES=15

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

RAW_CONTEXT=$(get_terminal_context "$TMUX_SESSION")

# Format context for Telegram readability (strip ANSI, convert tables to bullets)
if type format_for_telegram &>/dev/null; then
    CONTEXT=$(format_for_telegram "$RAW_CONTEXT")
else
    # Fallback: basic ANSI stripping if lib not loaded
    CONTEXT=$(echo "$RAW_CONTEXT" | sed 's/\x1b\[[0-9;]*[A-Za-z]//g')
fi

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

# HTML-escape context (user-generated content)
if type html_escape &>/dev/null; then
    ESCAPED_CONTEXT=$(html_escape "$CONTEXT")
    ESCAPED_SESSION=$(html_escape "$SESSION_NAME")
else
    # Fallback: inline escaping
    ESCAPED_CONTEXT="${CONTEXT//&/&amp;}"
    ESCAPED_CONTEXT="${ESCAPED_CONTEXT//</&lt;}"
    ESCAPED_CONTEXT="${ESCAPED_CONTEXT//>/&gt;}"
    ESCAPED_SESSION="${SESSION_NAME//&/&amp;}"
    ESCAPED_SESSION="${ESCAPED_SESSION//</&lt;}"
    ESCAPED_SESSION="${ESCAPED_SESSION//>/&gt;}"
fi

MESSAGE="$EMOJI <b>[$ESCAPED_SESSION] $HEADER</b>

<pre>$ESCAPED_CONTEXT</pre>

💬 Reply here or /preview for full context"

# Try sending with inline keyboard if options detected (Python + requests)
KEYBOARD_SENT=false
# Note: Python exits 1 when no options found (intentional fallback to curl).
# || true prevents set -e from aborting the script.
python3 -c '
import sys, json, re
try:
    import requests
except ImportError:
    sys.exit(2)

message, bot_token, chat_id = sys.argv[1], sys.argv[2], sys.argv[3]
topic_id = sys.argv[4] if len(sys.argv) > 4 else ""
session_name = sys.argv[5] if len(sys.argv) > 5 else "default"

pattern = re.compile(r"^\s*(?:(\d+)[.\)]\s+|#(\d+)\s+|\((\d+)\)\s+)(.+)$", re.MULTILINE)
matches = pattern.findall(message)

if len(matches) < 2:
    sys.exit(1)  # No options - fall back to curl

buttons = []
for match in matches[:8]:
    num = match[0] or match[1] or match[2]
    text = match[3].strip()
    label = f"{num}. {text[:37]}..." if len(text) > 37 else f"{num}. {text}"
    buttons.append([{"text": label, "callback_data": f"opt:{session_name[:40]}:{num}"}])

data = {
    "chat_id": chat_id,
    "text": message,
    "parse_mode": "HTML",
    "reply_markup": json.dumps({"inline_keyboard": buttons})
}
if topic_id:
    data["message_thread_id"] = topic_id

resp = requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", data=data, timeout=10)
sys.exit(0 if resp.json().get("ok") else 1)
' "$MESSAGE" "$TELEGRAM_BOT_TOKEN" "$TELEGRAM_CHAT_ID" "$TOPIC_ID" "$SESSION_NAME" 2>/dev/null && KEYBOARD_SENT=true || true

# Fallback: send via curl without keyboard (or if Python failed)
if [ "$KEYBOARD_SENT" = "false" ]; then
    # Build curl arguments
    CURL_ARGS=(
        -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage"
        -d "chat_id=$TELEGRAM_CHAT_ID"
        -d "parse_mode=HTML"
        --data-urlencode "text=$MESSAGE"
    )

    # Add topic ID if configured (for Forum groups)
    if [ -n "$TOPIC_ID" ]; then
        CURL_ARGS+=(-d "message_thread_id=$TOPIC_ID")
    fi

    # Send to Telegram with error handling
    ERROR_LOG="$CLAUDE_HOME/logs/notify-errors.log"
    mkdir -p "$(dirname "$ERROR_LOG")"

    RESPONSE=$(curl "${CURL_ARGS[@]}" 2>&1)
    CURL_EXIT=$?

    if [ $CURL_EXIT -ne 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$SESSION_NAME] curl exit $CURL_EXIT" >> "$ERROR_LOG"
    fi

    if ! echo "$RESPONSE" | grep -q '"ok":true'; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$SESSION_NAME] API error: $RESPONSE" >> "$ERROR_LOG"
    fi
fi

exit 0
