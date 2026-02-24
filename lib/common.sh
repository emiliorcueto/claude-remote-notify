#!/bin/bash
# =============================================================================
# lib/common.sh - Shared security and utility functions
# =============================================================================
#
# Source this file in shell scripts:
#   source "$(dirname "$0")/../lib/common.sh"
#
# =============================================================================

# Exit on error, undefined vars, and pipe failures
set -euo pipefail

# =============================================================================
# TEMP FILE HANDLING
# =============================================================================

# Array to track temp files for cleanup
_COMMON_TEMP_FILES=()

# Create secure temp file and register for cleanup
# Usage: MYFILE=$(create_temp_file "prefix" ".ext")
create_temp_file() {
    local prefix="${1:-tmp}"
    local suffix="${2:-.tmp}"
    local temp_file
    temp_file=$(mktemp -t "${prefix}-XXXXXX${suffix}")
    _COMMON_TEMP_FILES+=("$temp_file")
    echo "$temp_file"
}

# Create secure temp directory and register for cleanup
# Usage: MYDIR=$(create_temp_dir "prefix")
create_temp_dir() {
    local prefix="${1:-tmp}"
    local temp_dir
    temp_dir=$(mktemp -d -t "${prefix}-XXXXXX")
    _COMMON_TEMP_FILES+=("$temp_dir")
    echo "$temp_dir"
}

# Cleanup all registered temp files/dirs
cleanup_temp_files() {
    for f in "${_COMMON_TEMP_FILES[@]:-}"; do
        if [ -n "$f" ] && [ -e "$f" ]; then
            rm -rf "$f"
        fi
    done
    _COMMON_TEMP_FILES=()
}

# Register cleanup on exit (call once in main script)
register_cleanup_trap() {
    trap cleanup_temp_files EXIT
}

# =============================================================================
# SAFE VARIABLE SUBSTITUTION
# =============================================================================

# Safely substitute placeholders in a file using awk
# Usage: safe_substitute "file" "PLACEHOLDER" "value"
safe_substitute() {
    local file="$1"
    local placeholder="$2"
    local value="$3"

    if [ ! -f "$file" ]; then
        echo "Error: File not found: $file" >&2
        return 1
    fi

    local temp_file
    temp_file=$(mktemp)
    awk -v placeholder="$placeholder" -v value="$value" \
        '{gsub(placeholder, value); print}' "$file" > "$temp_file" \
        && mv "$temp_file" "$file"
}

# Safely substitute multiple placeholders in a file
# Usage: safe_substitute_multi "file" "KEY1=val1" "KEY2=val2" ...
safe_substitute_multi() {
    local file="$1"
    shift

    if [ ! -f "$file" ]; then
        echo "Error: File not found: $file" >&2
        return 1
    fi

    local temp_file
    temp_file=$(mktemp)
    cp "$file" "$temp_file"

    for pair in "$@"; do
        local key="${pair%%=*}"
        local value="${pair#*=}"
        awk -v placeholder="$key" -v value="$value" \
            '{gsub(placeholder, value); print}' "$temp_file" > "${temp_file}.new" \
            && mv "${temp_file}.new" "$temp_file"
    done

    mv "$temp_file" "$file"
}

# =============================================================================
# INPUT VALIDATION
# =============================================================================

# Validate session name (alphanumeric, dash, underscore only)
# Usage: validate_session_name "myproject"
validate_session_name() {
    local name="$1"
    if [[ ! "$name" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        echo "Error: Invalid session name. Use only alphanumeric, dash, underscore." >&2
        return 1
    fi
    echo "$name"
}

# Sanitize input for safe shell usage (remove dangerous chars)
# Usage: sanitized=$(sanitize_input "$user_input")
sanitize_input() {
    local input="$1"
    # Remove shell metacharacters
    echo "$input" | tr -cd 'a-zA-Z0-9 _.,@:/-'
}

# Validate path is within allowed directory
# Usage: validate_path_in_dir "/path/to/file" "/allowed/base"
validate_path_in_dir() {
    local path="$1"
    local base="$2"

    local resolved_path resolved_base
    resolved_path=$(cd "$(dirname "$path")" 2>/dev/null && pwd)/$(basename "$path")
    resolved_base=$(cd "$base" 2>/dev/null && pwd)

    if [[ ! "$resolved_path" == "$resolved_base"* ]]; then
        echo "Error: Path '$path' is outside allowed directory" >&2
        return 1
    fi
    echo "$resolved_path"
}

# =============================================================================
# SCRIPT VALIDATION
# =============================================================================

# Validate script is safe to execute
# Usage: validate_script "/path/to/script.sh"
validate_script() {
    local script="$1"

    # Must exist
    if [ ! -e "$script" ]; then
        echo "Error: Script not found: $script" >&2
        return 1
    fi

    # Must be a regular file
    if [ ! -f "$script" ]; then
        echo "Error: Not a regular file: $script" >&2
        return 1
    fi

    # Must not be a symlink (or resolve safely)
    if [ -L "$script" ]; then
        local target
        target=$(readlink -f "$script")
        if [ ! -f "$target" ]; then
            echo "Error: Symlink target not a file: $script" >&2
            return 1
        fi
    fi

    # Must be owned by current user or root
    local owner
    owner=$(stat -f %u "$script" 2>/dev/null || stat -c %u "$script" 2>/dev/null)
    if [ "$owner" != "$(id -u)" ] && [ "$owner" != "0" ]; then
        echo "Error: Script not owned by current user or root: $script" >&2
        return 1
    fi

    # Must not be world-writable
    if [ -w "$script" ] && [ "$(stat -f %Lp "$script" 2>/dev/null || stat -c %a "$script" 2>/dev/null)" != "${!#}" ]; then
        local perms
        perms=$(stat -f %Lp "$script" 2>/dev/null || stat -c %a "$script" 2>/dev/null)
        if [[ "$perms" == *2 ]] || [[ "$perms" == *3 ]] || [[ "$perms" == *6 ]] || [[ "$perms" == *7 ]]; then
            echo "Error: Script is world-writable: $script" >&2
            return 1
        fi
    fi

    echo "$script"
}

# =============================================================================
# LOGGING
# =============================================================================

# Log levels
LOG_LEVEL_DEBUG=0
LOG_LEVEL_INFO=1
LOG_LEVEL_WARN=2
LOG_LEVEL_ERROR=3

# Default log level
LOG_LEVEL="${LOG_LEVEL:-$LOG_LEVEL_INFO}"

# Colors (if terminal supports)
if [ -t 1 ]; then
    _LOG_RED='\033[0;31m'
    _LOG_GREEN='\033[0;32m'
    _LOG_YELLOW='\033[1;33m'
    _LOG_BLUE='\033[0;34m'
    _LOG_NC='\033[0m'
else
    _LOG_RED=''
    _LOG_GREEN=''
    _LOG_YELLOW=''
    _LOG_BLUE=''
    _LOG_NC=''
fi

log_debug() { [ "$LOG_LEVEL" -le "$LOG_LEVEL_DEBUG" ] && echo -e "${_LOG_BLUE}[DEBUG]${_LOG_NC} $*" >&2 || true; }
log_info()  { [ "$LOG_LEVEL" -le "$LOG_LEVEL_INFO" ]  && echo -e "${_LOG_GREEN}[INFO]${_LOG_NC} $*" >&2 || true; }
log_warn()  { [ "$LOG_LEVEL" -le "$LOG_LEVEL_WARN" ]  && echo -e "${_LOG_YELLOW}[WARN]${_LOG_NC} $*" >&2 || true; }
log_error() { [ "$LOG_LEVEL" -le "$LOG_LEVEL_ERROR" ] && echo -e "${_LOG_RED}[ERROR]${_LOG_NC} $*" >&2 || true; }

# =============================================================================
# SAFE CONFIG LOADING
# =============================================================================

# Allowed config keys (whitelist)
_ALLOWED_CONFIG_KEYS="TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID TELEGRAM_TOPIC_ID TMUX_SESSION NOTIFY_DEBOUNCE"

# Load config file safely without sourcing
# Usage: load_config_safely "/path/to/config.conf"
# Exports: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_TOPIC_ID, TMUX_SESSION
load_config_safely() {
    local config_file="$1"

    # File must exist
    if [ ! -f "$config_file" ]; then
        echo "Error: Config file not found: $config_file" >&2
        return 1
    fi

    # Check file ownership (must be current user or root)
    local file_owner
    file_owner=$(stat -f %u "$config_file" 2>/dev/null || stat -c %u "$config_file" 2>/dev/null)
    if [ "$file_owner" != "$(id -u)" ] && [ "$file_owner" != "0" ]; then
        echo "Error: Config file not owned by current user or root: $config_file" >&2
        return 1
    fi

    # Check file is not world-writable
    local perms
    perms=$(stat -f %Lp "$config_file" 2>/dev/null || stat -c %a "$config_file" 2>/dev/null)
    if [[ "$perms" == *2 ]] || [[ "$perms" == *3 ]] || [[ "$perms" == *6 ]] || [[ "$perms" == *7 ]]; then
        echo "Error: Config file is world-writable: $config_file" >&2
        return 1
    fi

    # Parse config safely - only extract known keys
    while IFS= read -r line || [ -n "$line" ]; do
        # Skip comments and empty lines
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line// }" ]] && continue

        # Extract key=value
        if [[ "$line" =~ ^[[:space:]]*([A-Z_]+)[[:space:]]*=[[:space:]]*(.*)$ ]]; then
            local key="${BASH_REMATCH[1]}"
            local value="${BASH_REMATCH[2]}"

            # Remove surrounding quotes
            value="${value#\"}"
            value="${value%\"}"
            value="${value#\'}"
            value="${value%\'}"

            # Only export whitelisted keys
            case " $_ALLOWED_CONFIG_KEYS " in
                *" $key "*)
                    export "$key"="$value"
                    ;;
            esac
        fi
    done < "$config_file"

    return 0
}

# Load config from session file or global fallback
# Usage: load_session_config "session_name" "/path/to/claude_home"
load_session_config() {
    local session_name="$1"
    local claude_home="${2:-$HOME/.claude}"
    local sessions_dir="$claude_home/sessions"
    local config_file="$sessions_dir/$session_name.conf"
    local global_config="$claude_home/telegram-remote.conf"

    if [ -f "$config_file" ]; then
        load_config_safely "$config_file"
    elif [ -f "$global_config" ]; then
        load_config_safely "$global_config"
    else
        echo "Error: No config found for session '$session_name'" >&2
        return 1
    fi
}

# =============================================================================
# NOTIFICATION CANCELLATION
# =============================================================================

# Cancel a pending delayed notification for a session.
# Reads the PID file, kills the background sleep+send process if alive,
# and removes the PID file.
#
# Usage: cancel_pending_notification "session_name" ["/path/to/claude_home"]
# Returns: 0 if cancelled or no pending notification, 1 on error
cancel_pending_notification() {
    local session_name="$1"
    local claude_home="${2:-${CLAUDE_HOME:-$HOME/.claude}}"
    local pid_file="$claude_home/notifications-pending/$session_name.pid"

    [ ! -f "$pid_file" ] && return 0

    local old_pid
    old_pid=$(cat "$pid_file" 2>/dev/null) || true

    if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
        kill "$old_pid" 2>/dev/null || true
    fi

    rm -f "$pid_file"
    return 0
}

# =============================================================================
# TELEGRAM VALIDATION
# =============================================================================

# Validate Telegram bot token format
# Usage: validate_bot_token "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890"
validate_bot_token() {
    local token="$1"
    # Format: digits:alphanumeric (typically 8-10 digits, colon, 35 chars)
    if [[ "$token" =~ ^[0-9]{8,10}:[A-Za-z0-9_-]{35}$ ]]; then
        return 0
    else
        echo "Error: Invalid bot token format" >&2
        return 1
    fi
}

# Validate Telegram chat ID format
# Usage: validate_chat_id "-1001234567890"
validate_chat_id() {
    local chat_id="$1"
    # Chat IDs are integers (positive for users, negative for groups/channels)
    if [[ "$chat_id" =~ ^-?[0-9]+$ ]]; then
        return 0
    else
        echo "Error: Invalid chat ID format (must be an integer)" >&2
        return 1
    fi
}

# Validate Telegram topic ID format (optional, can be empty)
# Usage: validate_topic_id "123"
validate_topic_id() {
    local topic_id="$1"
    # Topic IDs are positive integers, or empty
    if [ -z "$topic_id" ] || [[ "$topic_id" =~ ^[0-9]+$ ]]; then
        return 0
    else
        echo "Error: Invalid topic ID format (must be a positive integer)" >&2
        return 1
    fi
}

# Resolve session identifier (name or topic ID) to session name
# Priority: exact session config match > topic ID scan > passthrough
# Usage: resolved=$(resolve_session_identifier "70" "/path/to/sessions")
resolve_session_identifier() {
    local identifier="$1"
    local sessions_dir="$2"

    # Session name match takes priority (config file exists)
    if [ -f "$sessions_dir/$identifier.conf" ]; then
        echo "$identifier"
        return 0
    fi

    # Numeric identifier → scan configs for matching TELEGRAM_TOPIC_ID
    if [[ "$identifier" =~ ^[0-9]+$ ]]; then
        local match_count=0
        local match_name=""
        local match_names=""

        local _conf
        for _conf in "$sessions_dir"/*.conf; do
            [ -f "$_conf" ] || continue
            local _name
            _name=$(basename "$_conf" .conf)
            local _topic_id=""
            _topic_id=$(grep "^TELEGRAM_TOPIC_ID" "$_conf" 2>/dev/null \
                | cut -d'=' -f2 | tr -d '"' | tr -d "'")

            if [ "$_topic_id" = "$identifier" ]; then
                match_count=$((match_count + 1))
                match_name="$_name"
                match_names="$match_names $_name"
            fi
        done

        if [ "$match_count" -eq 1 ]; then
            echo "$match_name"
            return 0
        elif [ "$match_count" -gt 1 ]; then
            echo "Error: Topic ID '$identifier' matches multiple sessions:$match_names" >&2
            return 1
        fi

        echo "Error: No session found with topic ID '$identifier'" >&2
        echo "Use 'claude-remote --list' to see available sessions." >&2
        return 1
    fi

    # Non-numeric, no config match → passthrough for downstream handling
    echo "$identifier"
    return 0
}

# =============================================================================
# SENSITIVE DATA MASKING
# =============================================================================

# Mask sensitive string for safe logging
# Usage: masked=$(mask_sensitive "secret-value" 3 2)  # show first 3, last 2
mask_sensitive() {
    local value="$1"
    local show_start="${2:-3}"
    local show_end="${3:-2}"
    local len=${#value}

    if [ "$len" -le $((show_start + show_end + 3)) ]; then
        # Too short to mask meaningfully
        echo "***"
    else
        echo "${value:0:$show_start}...${value: -$show_end}"
    fi
}

# =============================================================================
# URL ENCODING
# =============================================================================

# URL-encode a string for safe use in URLs
# Usage: encoded=$(urlencode "hello world")
urlencode() {
    local string="$1"
    python3 -c "import urllib.parse; print(urllib.parse.quote('$string', safe=''))"
}

# URL-encode using only shell (no python dependency)
# Usage: encoded=$(urlencode_shell "hello world")
urlencode_shell() {
    local string="$1"
    local length="${#string}"
    local encoded=""
    local i char

    for (( i = 0; i < length; i++ )); do
        char="${string:i:1}"
        case "$char" in
            [a-zA-Z0-9.~_-])
                encoded+="$char"
                ;;
            *)
                encoded+=$(printf '%%%02X' "'$char")
                ;;
        esac
    done
    echo "$encoded"
}

# =============================================================================
# HTML ESCAPING
# =============================================================================

# Escape HTML special characters for Telegram parse_mode=HTML
# Usage: escaped=$(html_escape "$text")
html_escape() {
    local text="$1"
    text="${text//&/&amp;}"
    text="${text//</&lt;}"
    text="${text//>/&gt;}"
    echo "$text"
}

# =============================================================================
# TELEGRAM FORMATTING
# =============================================================================

# Format terminal output for Telegram readability
# - Strips ANSI escape codes
# - Converts ASCII/Unicode tables to bullet points
# - Preserves basic markdown (bold, italic, code)
# Usage: formatted=$(format_for_telegram "$raw_text")
format_for_telegram() {
    local input="$1"

    python3 -c '
import re
import sys
import unicodedata

def format_for_telegram(text):
    # Strip ANSI escape codes
    ansi_pattern = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b[^\x1b]*")
    text = ansi_pattern.sub("", text)

    # Strip other control characters (except newline, tab)
    def clean_char(c):
        if c in "\n\t":
            return c
        if ord(c) < 32:
            return ""
        cat = unicodedata.category(c)
        if cat in ("Cc", "Cf"):  # Control chars, format chars
            return ""
        return c

    text = "".join(clean_char(c) for c in text)

    # Box-drawing characters (Unicode)
    box_chars = "─━│┌┐└┘├┤┬┴┼╭╮╯╰═║╔╗╚╝╠╣╦╩╬"

    # Pattern for decorative/border lines (box chars, underscores, dashes, equals)
    decorative_pattern = re.compile(r"^[\s" + re.escape(box_chars) + r"_=\-\+]+$")

    # Pattern for lines that are only whitespace (including non-breaking spaces)
    whitespace_only = re.compile(r"^[\s\u00a0\u2000-\u200f\u2028\u2029\u202f\u205f\u3000]*$")

    lines = text.split("\n")
    result = []
    table_rows = []
    in_table = False
    header_row = None

    def is_decorative_line(line):
        """Check if line is decorative (borders, separators, whitespace-only)"""
        stripped = line.strip()
        if not stripped:
            return False
        if decorative_pattern.match(stripped):
            return True
        if whitespace_only.match(line):
            return True
        # Table separator lines like |------|------| or |======|======|
        normalized = stripped.replace("│", "|")
        if normalized.startswith("|") and normalized.endswith("|"):
            inner = normalized[1:-1]  # Remove outer pipes
            # If inner content is only dashes, equals, colons, pipes, spaces - its a separator
            if re.match(r"^[\-=:\|\s\+]+$", inner):
                return True
        return False

    def is_table_row(line):
        """Check if line is a proper table row - must start AND end with | or │"""
        stripped = line.strip()
        if not stripped:
            return False
        # Normalize to ASCII pipe
        normalized = stripped.replace("│", "|")
        # Strict: must start AND end with pipe (standard markdown table format)
        return normalized.startswith("|") and normalized.endswith("|")

    def extract_cells(line):
        """Extract cell content from a table row"""
        line = line.replace("│", "|")
        cells = [cell.strip() for cell in line.split("|")]
        cells = [c for c in cells if c]
        return cells

    def flush_table():
        """Convert accumulated table rows to bullet points"""
        nonlocal table_rows, header_row
        bullets = []

        for row in table_rows:
            cells = extract_cells(row)
            if not cells:
                continue
            if header_row and cells == header_row:
                continue

            if len(cells) == 1:
                bullets.append(f"• {cells[0]}")
            elif len(cells) == 2:
                bullets.append(f"• {cells[0]} — {cells[1]}")
            else:
                sep = " — "
                bullets.append(f"• {sep.join(cells)}")

        table_rows = []
        header_row = None
        return bullets

    for line in lines:
        # Skip whitespace-only lines
        if whitespace_only.match(line):
            continue

        # Skip decorative/border lines
        if is_decorative_line(line):
            if not in_table and table_rows:
                result.extend(flush_table())
            in_table = True
            continue

        if is_table_row(line):
            in_table = True
            cells = extract_cells(line)
            if not table_rows and cells:
                is_header = all(len(c) < 30 and c and not c[0].isdigit() and c[0] != "#" for c in cells)
                if is_header:
                    header_row = cells
            table_rows.append(line)
        else:
            if in_table or table_rows:
                result.extend(flush_table())
                in_table = False
            result.append(line)

    if table_rows:
        result.extend(flush_table())

    # Remove consecutive empty lines
    cleaned = []
    prev_empty = False
    for line in result:
        is_empty = not line.strip()
        if is_empty and prev_empty:
            continue
        cleaned.append(line)
        prev_empty = is_empty

    return "\n".join(cleaned)

text = sys.argv[1] if len(sys.argv) > 1 else ""
print(format_for_telegram(text))
' "$input"
}
