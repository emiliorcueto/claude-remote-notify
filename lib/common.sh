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
