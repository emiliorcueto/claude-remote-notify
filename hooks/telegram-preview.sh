#!/bin/bash
# =============================================================================
# telegram-preview.sh - Capture Claude output with colors (Multi-Session)
# =============================================================================
#
# Sends terminal output as styled HTML document to a specific Telegram Topic.
#
# Usage:
#   telegram-preview.sh [lines|back N] [--session NAME]
#
# Environment:
#   CLAUDE_SESSION - Session name (default: "default")
#
# =============================================================================

set -e

# -----------------------------------------------------------------------------
# Parse Arguments
# -----------------------------------------------------------------------------

MODE="lines"
VALUE=50
SESSION_NAME="${CLAUDE_SESSION:-default}"

show_help() {
    echo "═══════════════════════════════════════════"
    echo "  /remote-preview-output - Terminal Preview"
    echo "═══════════════════════════════════════════"
    echo ""
    echo "Send your terminal output to Telegram as a styled HTML"
    echo "document with FULL COLOR PRESERVATION."
    echo ""
    echo "Usage: /remote-preview-output [argument]"
    echo ""
    echo "Arguments:"
    echo ""
    echo "  (none)    Send last 50 lines of terminal output"
    echo "            Example: /remote-preview-output"
    echo ""
    echo "  <N>       Send last N lines of terminal output"
    echo "            Example: /remote-preview-output 100"
    echo "            Example: /remote-preview-output 200"
    echo ""
    echo "  back <N>  Send the Nth previous exchange"
    echo "            Attempts to detect prompt boundaries and"
    echo "            extract a specific conversation exchange."
    echo "            - back 0 = current/most recent response"
    echo "            - back 1 = previous exchange"
    echo "            - back 2 = two exchanges ago"
    echo "            Example: /remote-preview-output back 1"
    echo ""
    echo "  help      Show this help message"
    echo "            Example: /remote-preview-output help"
    echo ""
    echo "Features:"
    echo "  ✓ Terminal colors preserved (green/red diffs, etc.)"
    echo "  ✓ Code syntax highlighting maintained"
    echo "  ✓ Emojis display correctly"
    echo "  ✓ Opens inside Telegram app (tap the file)"
    echo "  ✓ Pinch to zoom, scroll through output"
    echo ""
    echo "Output:"
    echo "  Sends an HTML file to your Telegram chat/topic."
    echo "  Tap the file to view it in Telegram's built-in viewer."
    echo ""
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --session|-s)
            SESSION_NAME="$2"
            shift 2
            ;;
        back)
            MODE="back"
            VALUE="${2:-0}"
            shift 2
            ;;
        [0-9]*)
            MODE="lines"
            VALUE="$1"
            shift
            ;;
        help|-h|--help)
            show_help
            exit 0
            ;;
        *)
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
TMUX_SESSION="${TMUX_SESSION:-claude-$SESSION_NAME}"

# Use mktemp for secure temp file creation (prevents symlink attacks)
TEMP_HTML=$(mktemp -t "claude-terminal-${SESSION_NAME}-XXXXXX.html")
trap 'rm -f "$TEMP_HTML"' EXIT

# -----------------------------------------------------------------------------
# Load Configuration
# -----------------------------------------------------------------------------

if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
elif [ -f "$GLOBAL_CONFIG" ]; then
    source "$GLOBAL_CONFIG"
else
    echo "Error: No config found for session '$SESSION_NAME'"
    exit 1
fi

if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "Error: Telegram credentials not configured"
    exit 1
fi

TOPIC_ID="${TELEGRAM_TOPIC_ID:-}"

# -----------------------------------------------------------------------------
# Check Dependencies
# -----------------------------------------------------------------------------

check_ansi2html() {
    if ! python3 -c "import ansi2html" 2>/dev/null; then
        echo "Error: ansi2html not installed"
        echo "Install with: pip install --user ansi2html"
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

capture_terminal_with_ansi() {
    local lines="${1:-50}"
    
    if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        echo "Error: tmux session '$TMUX_SESSION' not found"
        exit 1
    fi
    
    tmux capture-pane -t "$TMUX_SESSION" -pS -"$lines" -e 2>/dev/null
}

convert_to_html() {
    local title="$1"
    local session="$2"
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    
    python3 << PYTHON_SCRIPT - "$title" "$session" "$timestamp"
import sys
from ansi2html import Ansi2HTMLConverter

title = sys.argv[1] if len(sys.argv) > 1 else "Terminal Output"
session = sys.argv[2] if len(sys.argv) > 2 else "default"
timestamp = sys.argv[3] if len(sys.argv) > 3 else ""

ansi_input = sys.stdin.read()

conv = Ansi2HTMLConverter(inline=True, dark_bg=True, scheme='dracula')
html_body = conv.convert(ansi_input, full=False)

html_doc = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>[{session}] {title}</title>
    <style>
        body {{
            background-color: #1e1e1e;
            color: #d4d4d4;
            font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.4;
            padding: 12px;
            margin: 0;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .header {{
            background-color: #2d2d2d;
            color: #9cdcfe;
            padding: 8px 12px;
            margin: -12px -12px 12px -12px;
            border-bottom: 1px solid #404040;
            font-size: 11px;
        }}
        .session {{
            color: #4ec9b0;
            font-weight: bold;
        }}
        .timestamp {{
            color: #808080;
            float: right;
        }}
        .ansi1 {{ font-weight: bold; }}
        .ansi2 {{ font-style: italic; }}
        .ansi4 {{ text-decoration: underline; }}
        .ansi9 {{ text-decoration: line-through; }}
    </style>
</head>
<body>
    <div class="header">
        📺 <span class="session">[{session}]</span> {title}
        <span class="timestamp">{timestamp}</span>
    </div>
{html_body}
</body>
</html>'''

print(html_doc)
PYTHON_SCRIPT
}

send_html_document() {
    local filepath="$1"
    local caption="$2"
    
    local curl_args=(
        -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendDocument"
        -F "chat_id=$TELEGRAM_CHAT_ID"
        -F "document=@$filepath"
        -F "caption=$caption"
    )
    
    # Add topic ID if configured
    if [ -n "$TOPIC_ID" ]; then
        curl_args+=(-F "message_thread_id=$TOPIC_ID")
    fi
    
    local response
    response=$(curl "${curl_args[@]}" 2>&1)
    
    if echo "$response" | grep -q '"ok":true'; then
        return 0
    else
        echo "Telegram API error: $response" >&2
        return 1
    fi
}

find_exchange() {
    local back="${1:-0}"
    local full_buffer
    
    full_buffer=$(capture_terminal_with_ansi 2000)
    
    echo "$full_buffer" | awk -v back="$back" '
    BEGIN { 
        section = 0
        buffer = ""
        sections[0] = ""
    }
    
    /^> / || /^You:/ || /^Human:/ || /^───/ || /^━━━/ {
        if (buffer != "") {
            sections[section] = buffer
            section++
        }
        buffer = $0 "\n"
        next
    }
    
    {
        buffer = buffer $0 "\n"
    }
    
    END {
        if (buffer != "") {
            sections[section] = buffer
        }
        
        target = section - back
        if (target < 0) target = 0
        
        print sections[target]
    }
    '
}

# -----------------------------------------------------------------------------
# Main Logic
# -----------------------------------------------------------------------------

main() {
    check_ansi2html
    
    local content
    local title
    local caption
    
    case "$MODE" in
        lines)
            content=$(capture_terminal_with_ansi "$VALUE")
            title="Terminal Output (last $VALUE lines)"
            caption="📺 [$SESSION_NAME] Last $VALUE lines"
            ;;
        back)
            content=$(find_exchange "$VALUE")
            if [ "$VALUE" -eq 0 ]; then
                title="Current Response"
                caption="📺 [$SESSION_NAME] Current response"
            else
                title="Previous Exchange (-$VALUE)"
                caption="📺 [$SESSION_NAME] Previous exchange (-$VALUE)"
            fi
            ;;
    esac
    
    if [ -z "$content" ]; then
        echo "⚠ No content captured"
        exit 0
    fi
    
    echo "[$SESSION_NAME] Converting to HTML..."
    echo "$content" | convert_to_html "$title" "$SESSION_NAME" > "$TEMP_HTML"
    
    local filesize=$(wc -c < "$TEMP_HTML")
    echo "Generated: $TEMP_HTML ($filesize bytes)"
    
    echo "Sending to Telegram..."
    if [ -n "$TOPIC_ID" ]; then
        echo "  Topic ID: $TOPIC_ID"
    fi
    
    if send_html_document "$TEMP_HTML" "$caption"; then
        echo "✓ Sent to Telegram"
        echo "  Tap the file to view with full colors!"
    else
        echo "✗ Failed to send"
        exit 1
    fi
    # Note: TEMP_HTML cleanup handled by EXIT trap
}

main
