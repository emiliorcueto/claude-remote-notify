#!/bin/bash
# =============================================================================
# remote-notify.sh - Unified notification control for Claude Remote
# =============================================================================
#
# Usage:
#   remote-notify.sh <command> [--session NAME]
#
# Commands:
#   on       - Enable notifications
#   off      - Disable notifications
#   status   - Check notification state
#   config   - Show full configuration
#   start    - Start Telegram listener
#   kill     - Stop Telegram listener
#
# =============================================================================

set -e

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
SESSION_NAME="${CLAUDE_SESSION:-default}"
NOTIFY_FLAG="$CLAUDE_HOME/notifications-enabled"

# Load shared library
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LIB_DIR="${SCRIPT_DIR%/hooks}/lib"
if [ -f "$LIB_DIR/common.sh" ]; then
    source "$LIB_DIR/common.sh"
    _USE_SAFE_CONFIG=true
else
    _USE_SAFE_CONFIG=false
fi

# Colors (for terminal output)
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# -----------------------------------------------------------------------------
# Parse Arguments
# -----------------------------------------------------------------------------

COMMAND=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --session|-s)
            SESSION_NAME="$2"
            shift 2
            ;;
        on|off|status|config|start|kill|help)
            COMMAND="$1"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

get_config_file() {
    local session="$1"
    local session_conf="$CLAUDE_HOME/sessions/$session.conf"
    local global_conf="$CLAUDE_HOME/telegram-remote.conf"
    
    if [ -f "$session_conf" ]; then
        echo "$session_conf"
    elif [ -f "$global_conf" ]; then
        echo "$global_conf"
    else
        echo ""
    fi
}

get_pid_file() {
    echo "$CLAUDE_HOME/pids/listener-$SESSION_NAME.pid"
}

listener_running() {
    local pid_file=$(get_pid_file)
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

send_telegram() {
    local message="$1"
    local config_file=$(get_config_file "$SESSION_NAME")

    if [ -z "$config_file" ] || [ ! -f "$config_file" ]; then
        return 1
    fi

    # Use safe config loading if available
    if [ "$_USE_SAFE_CONFIG" = true ]; then
        load_config_safely "$config_file" 2>/dev/null || return 1
    else
        source "$config_file"
    fi

    if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
        return 1
    fi

    local curl_args=(
        -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage"
        -d "chat_id=$TELEGRAM_CHAT_ID"
        --data-urlencode "text=$message"
    )

    if [ -n "$TELEGRAM_TOPIC_ID" ]; then
        curl_args+=(-d "message_thread_id=$TELEGRAM_TOPIC_ID")
    fi

    curl "${curl_args[@]}" > /dev/null 2>&1
}

# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------

cmd_on() {
    touch "$NOTIFY_FLAG"
    echo -e "${GREEN}✓${NC} Notifications enabled"
    send_telegram "🔔 [$SESSION_NAME] Notifications enabled"
}

cmd_off() {
    rm -f "$NOTIFY_FLAG"
    echo -e "${GREEN}✓${NC} Notifications disabled"
    send_telegram "🔕 [$SESSION_NAME] Notifications disabled"
}

cmd_status() {
    echo "Session: $SESSION_NAME"
    echo ""
    
    # Notification status
    if [ -f "$NOTIFY_FLAG" ]; then
        echo -e "Notifications: ${GREEN}enabled${NC}"
    else
        echo -e "Notifications: ${RED}disabled${NC}"
    fi
    
    # Listener status
    if listener_running; then
        local pid=$(cat "$(get_pid_file)")
        echo -e "Listener: ${GREEN}running${NC} (PID: $pid)"
    else
        echo -e "Listener: ${RED}not running${NC}"
    fi
    
    # tmux status
    local tmux_name="claude-$SESSION_NAME"
    if tmux has-session -t "$tmux_name" 2>/dev/null; then
        echo -e "tmux session: ${GREEN}running${NC} ($tmux_name)"
    else
        echo -e "tmux session: ${YELLOW}not found${NC} ($tmux_name)"
    fi
}

cmd_config() {
    echo "═══════════════════════════════════════════"
    echo "  Claude Remote Configuration"
    echo "═══════════════════════════════════════════"
    echo ""
    echo "Session: $SESSION_NAME"
    echo ""
    
    # Config file
    local config_file=$(get_config_file "$SESSION_NAME")
    if [ -n "$config_file" ] && [ -f "$config_file" ]; then
        echo -e "Config file: ${GREEN}$config_file${NC}"
        echo ""
        echo "Contents:"
        echo "─────────────────────────────────────────"
        grep -v "^#" "$config_file" | grep -v "^$" | while read line; do
            # Mask the token
            if [[ "$line" == *"BOT_TOKEN"* ]]; then
                local token=$(echo "$line" | cut -d'=' -f2 | tr -d '"' | tr -d "'")
                echo "  TELEGRAM_BOT_TOKEN=${token:0:10}...${token: -5}"
            else
                echo "  $line"
            fi
        done
        echo "─────────────────────────────────────────"
    else
        echo -e "Config file: ${RED}not found${NC}"
        echo "  Expected: $CLAUDE_HOME/sessions/$SESSION_NAME.conf"
        echo "  Or global: $CLAUDE_HOME/telegram-remote.conf"
    fi
    
    echo ""
    
    # Status summary
    cmd_status
}

cmd_start() {
    if listener_running; then
        local pid=$(cat "$(get_pid_file)")
        echo -e "${YELLOW}!${NC} Listener already running (PID: $pid)"
        return 0
    fi
    
    local listener="$CLAUDE_HOME/hooks/telegram-listener.py"
    
    if [ ! -f "$listener" ]; then
        echo -e "${RED}✗${NC} Listener not found: $listener"
        return 1
    fi
    
    echo "Starting Telegram listener for session: $SESSION_NAME"
    
    mkdir -p "$CLAUDE_HOME/logs" "$CLAUDE_HOME/pids"
    
    nohup python3 "$listener" --session "$SESSION_NAME" \
        >> "$CLAUDE_HOME/logs/listener-$SESSION_NAME.log" 2>&1 &
    
    sleep 1
    
    if listener_running; then
        local pid=$(cat "$(get_pid_file)")
        echo -e "${GREEN}✓${NC} Listener started (PID: $pid)"
        send_telegram "🚀 [$SESSION_NAME] Listener started"
    else
        echo -e "${RED}✗${NC} Failed to start listener"
        echo "Check log: $CLAUDE_HOME/logs/listener-$SESSION_NAME.log"
        return 1
    fi
}

cmd_kill() {
    local pid_file=$(get_pid_file)
    
    if ! listener_running; then
        echo -e "${YELLOW}!${NC} Listener not running"
        return 0
    fi
    
    local pid=$(cat "$pid_file")
    echo "Stopping listener (PID: $pid)..."
    
    kill "$pid" 2>/dev/null || true
    rm -f "$pid_file"
    
    sleep 1
    
    if ! listener_running; then
        echo -e "${GREEN}✓${NC} Listener stopped"
    else
        echo -e "${YELLOW}!${NC} Sending SIGKILL..."
        kill -9 "$pid" 2>/dev/null || true
        rm -f "$pid_file"
        echo -e "${GREEN}✓${NC} Listener killed"
    fi
}

cmd_help() {
    echo "═══════════════════════════════════════════"
    echo "  /remote-notify - Notification Control"
    echo "═══════════════════════════════════════════"
    echo ""
    echo "Usage: /remote-notify <command>"
    echo ""
    echo "Commands:"
    echo ""
    echo "  on      Enable Telegram notifications"
    echo "          Notifications are sent when Claude needs input,"
    echo "          completes a task, or encounters an error."
    echo ""
    echo "  off     Disable Telegram notifications"
    echo "          The listener continues running (you can still"
    echo "          SEND messages to Claude, just no alerts)."
    echo ""
    echo "  status  Quick status check"
    echo "          Shows: notification state, listener state,"
    echo "          and tmux session state."
    echo ""
    echo "  config  Full configuration display"
    echo "          Shows config file contents (token masked),"
    echo "          Topic ID, and all status information."
    echo ""
    echo "  start   Start the Telegram listener"
    echo "          Launches the background process that receives"
    echo "          messages from Telegram and injects them into"
    echo "          your Claude session."
    echo ""
    echo "  kill    Stop the Telegram listener"
    echo "          Terminates the listener process. You won't"
    echo "          receive messages until you start it again."
    echo ""
    echo "  help    Show this help message"
    echo ""
    echo "Examples:"
    echo "  /remote-notify on"
    echo "  /remote-notify status"
    echo "  /remote-notify config"
    echo ""
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

case "$COMMAND" in
    on)
        cmd_on
        ;;
    off)
        cmd_off
        ;;
    status)
        cmd_status
        ;;
    config)
        cmd_config
        ;;
    start)
        cmd_start
        ;;
    kill)
        cmd_kill
        ;;
    help|"")
        cmd_help
        ;;
    *)
        echo "Unknown command: $COMMAND"
        echo ""
        cmd_help
        exit 1
        ;;
esac
