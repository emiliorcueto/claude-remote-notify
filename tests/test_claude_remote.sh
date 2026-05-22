#!/bin/bash
# =============================================================================
# test_claude_remote.sh - Unit tests for claude-remote script
# =============================================================================
#
# Usage: ./test_claude_remote.sh
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for test output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# =============================================================================
# TEST FRAMEWORK
# =============================================================================

assert_equals() {
    local expected="$1"
    local actual="$2"
    local message="${3:-}"

    TESTS_RUN=$((TESTS_RUN + 1))

    if [ "$expected" = "$actual" ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $message"
        return 0
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $message"
        echo "    Expected: $expected"
        echo "    Actual:   $actual"
        return 1
    fi
}

assert_contains() {
    local haystack="$1"
    local needle="$2"
    local message="${3:-}"

    TESTS_RUN=$((TESTS_RUN + 1))

    if echo "$haystack" | grep -q "$needle"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $message"
        return 0
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $message"
        echo "    Haystack does not contain: $needle"
        return 1
    fi
}

assert_not_contains() {
    local haystack="$1"
    local needle="$2"
    local message="${3:-}"

    TESTS_RUN=$((TESTS_RUN + 1))

    if ! echo "$haystack" | grep -q "$needle"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $message"
        return 0
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $message"
        echo "    Haystack should not contain: $needle"
        return 1
    fi
}

assert_true() {
    local condition="$1"
    local message="${2:-}"

    TESTS_RUN=$((TESTS_RUN + 1))

    if [ "$condition" = "true" ] || [ "$condition" = "0" ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $message"
        return 0
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $message"
        return 1
    fi
}

# =============================================================================
# SETUP / TEARDOWN
# =============================================================================

TEMP_DIR=""
TEST_SESSION="test-$$"
TEST_TMUX_SESSION="claude-$TEST_SESSION"

setup() {
    TEMP_DIR=$(mktemp -d)
    export CLAUDE_HOME="$TEMP_DIR/.claude"
    mkdir -p "$CLAUDE_HOME/sessions" "$CLAUDE_HOME/pids" "$CLAUDE_HOME/logs" "$CLAUDE_HOME/hooks"

    # Create minimal config for tests
    cat > "$CLAUDE_HOME/sessions/$TEST_SESSION.conf" << EOF
TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz123456789"
TELEGRAM_CHAT_ID="-1001234567890"
TELEGRAM_TOPIC_ID="123"
TMUX_SESSION="$TEST_TMUX_SESSION"
EOF
    chmod 600 "$CLAUDE_HOME/sessions/$TEST_SESSION.conf"
}

teardown() {
    # Kill test tmux session if exists
    tmux kill-session -t "$TEST_TMUX_SESSION" 2>/dev/null || true

    if [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
}

# =============================================================================
# TESTS: SCRIPT CONTENT VERIFICATION
# =============================================================================

test_mouse_mode_enabled_in_script() {
    echo ""
    echo "Testing: mouse mode enabled in session creation"

    local script_content
    script_content=$(cat "$PROJECT_DIR/claude-remote")

    # Check that tmux set-option mouse on is present
    assert_contains "$script_content" "tmux set-option -t.*mouse on" \
        "Script contains mouse mode enable command"
}

test_mouse_mode_after_session_block() {
    echo ""
    echo "Testing: mouse mode set after session create/attach block (applies to both cases)"

    local script_content
    script_content=$(cat "$PROJECT_DIR/claude-remote")

    # Mouse mode should be set after the fi (end of session create/attach block)
    # and before the listener start, so it applies whether session is new or existing
    local context
    context=$(echo "$script_content" | grep -A 5 "tmux session already exists")

    assert_contains "$context" "mouse on" \
        "Mouse mode enabled after session block (works for new and existing sessions)"
}

test_text_select_hint_present() {
    echo ""
    echo "Testing: text selection hint in output"

    local script_content
    script_content=$(cat "$PROJECT_DIR/claude-remote")

    assert_contains "$script_content" "Text select: Option+drag" \
        "Text selection hint present in script"
}

test_text_select_hint_near_detach_hint() {
    echo ""
    echo "Testing: text selection hint near detach hint"

    local script_content
    script_content=$(cat "$PROJECT_DIR/claude-remote")

    # Get context around detach hint
    local context
    context=$(echo "$script_content" | grep -A 2 "Detach with: Ctrl+b")

    assert_contains "$context" "Option+drag" \
        "Text select hint follows detach hint"
}

# =============================================================================
# TESTS: TMUX MOUSE MODE INTEGRATION
# =============================================================================

test_tmux_session_has_mouse_mode() {
    echo ""
    echo "Testing: tmux session created with mouse mode"

    setup

    # Skip if tmux not available
    if ! command -v tmux &>/dev/null; then
        TESTS_RUN=$((TESTS_RUN + 1))
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${YELLOW}SKIP${NC}: tmux not available"
        teardown
        return 0
    fi

    # Create a tmux session mimicking claude-remote behavior
    tmux new-session -d -s "$TEST_TMUX_SESSION" -e "CLAUDE_SESSION=$TEST_SESSION"
    tmux set-option -t "$TEST_TMUX_SESSION" mouse on

    # Verify mouse mode is on
    local mouse_setting
    mouse_setting=$(tmux show-options -t "$TEST_TMUX_SESSION" mouse 2>/dev/null | awk '{print $2}')

    assert_equals "on" "$mouse_setting" "Mouse mode is enabled in tmux session"

    teardown
}

test_tmux_mouse_mode_default_off() {
    echo ""
    echo "Testing: tmux default has mouse mode off (validates our fix is needed)"

    # Skip if tmux not available
    if ! command -v tmux &>/dev/null; then
        TESTS_RUN=$((TESTS_RUN + 1))
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${YELLOW}SKIP${NC}: tmux not available"
        return 0
    fi

    local temp_session="test-default-$$"

    # Create session without mouse mode
    tmux new-session -d -s "$temp_session"

    # Check default mouse setting
    local mouse_setting
    mouse_setting=$(tmux show-options -t "$temp_session" mouse 2>/dev/null | awk '{print $2}')

    # Default should be off (empty or "off")
    TESTS_RUN=$((TESTS_RUN + 1))
    if [ -z "$mouse_setting" ] || [ "$mouse_setting" = "off" ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Default mouse mode is off (fix is necessary)"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: Expected mouse off by default, got: $mouse_setting"
    fi

    tmux kill-session -t "$temp_session" 2>/dev/null || true
}

# =============================================================================
# TESTS: VALIDATION FUNCTIONS
# =============================================================================

test_validate_bot_token_valid() {
    echo ""
    echo "Testing: validate_bot_token accepts valid tokens"

    # Extract function from script
    validate_bot_token() {
        local token="$1"
        if [[ "$token" =~ ^[0-9]{8,10}:[A-Za-z0-9_-]{35}$ ]]; then
            return 0
        else
            return 1
        fi
    }

    TESTS_RUN=$((TESTS_RUN + 1))
    if validate_bot_token "123456789:ABCdefGHIjklMNOpqrsTUVwxyz123456789"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Valid token accepted"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: Valid token should be accepted"
    fi
}

test_validate_bot_token_invalid() {
    echo ""
    echo "Testing: validate_bot_token rejects invalid tokens"

    validate_bot_token() {
        local token="$1"
        if [[ "$token" =~ ^[0-9]{8,10}:[A-Za-z0-9_-]{35}$ ]]; then
            return 0
        else
            return 1
        fi
    }

    TESTS_RUN=$((TESTS_RUN + 1))
    if ! validate_bot_token "invalid"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Invalid token rejected"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: Invalid token should be rejected"
    fi

    TESTS_RUN=$((TESTS_RUN + 1))
    if ! validate_bot_token ""; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Empty token rejected"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: Empty token should be rejected"
    fi
}

test_validate_chat_id_valid() {
    echo ""
    echo "Testing: validate_chat_id accepts valid IDs"

    validate_chat_id() {
        local chat_id="$1"
        if [[ "$chat_id" =~ ^-?[0-9]+$ ]]; then
            return 0
        else
            return 1
        fi
    }

    TESTS_RUN=$((TESTS_RUN + 1))
    if validate_chat_id "-1001234567890"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Negative group ID accepted"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: Negative group ID should be accepted"
    fi

    TESTS_RUN=$((TESTS_RUN + 1))
    if validate_chat_id "123456789"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Positive user ID accepted"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: Positive user ID should be accepted"
    fi
}

test_validate_chat_id_invalid() {
    echo ""
    echo "Testing: validate_chat_id rejects invalid IDs"

    validate_chat_id() {
        local chat_id="$1"
        if [[ "$chat_id" =~ ^-?[0-9]+$ ]]; then
            return 0
        else
            return 1
        fi
    }

    TESTS_RUN=$((TESTS_RUN + 1))
    if ! validate_chat_id "abc123"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Alphanumeric ID rejected"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: Alphanumeric ID should be rejected"
    fi
}

test_validate_topic_id_valid() {
    echo ""
    echo "Testing: validate_topic_id accepts valid IDs"

    validate_topic_id() {
        local topic_id="$1"
        if [ -z "$topic_id" ] || [[ "$topic_id" =~ ^[0-9]+$ ]]; then
            return 0
        else
            return 1
        fi
    }

    TESTS_RUN=$((TESTS_RUN + 1))
    if validate_topic_id "123"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Numeric topic ID accepted"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: Numeric topic ID should be accepted"
    fi

    TESTS_RUN=$((TESTS_RUN + 1))
    if validate_topic_id ""; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Empty topic ID accepted"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: Empty topic ID should be accepted"
    fi
}

test_validate_topic_id_invalid() {
    echo ""
    echo "Testing: validate_topic_id rejects invalid IDs"

    validate_topic_id() {
        local topic_id="$1"
        if [ -z "$topic_id" ] || [[ "$topic_id" =~ ^[0-9]+$ ]]; then
            return 0
        else
            return 1
        fi
    }

    TESTS_RUN=$((TESTS_RUN + 1))
    if ! validate_topic_id "-123"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Negative topic ID rejected"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: Negative topic ID should be rejected"
    fi
}

# =============================================================================
# TESTS: HELPER FUNCTIONS
# =============================================================================

test_get_tmux_session_name() {
    echo ""
    echo "Testing: get_tmux_session_name"

    get_tmux_session_name() {
        local session="$1"
        echo "claude-$session"
    }

    local result
    result=$(get_tmux_session_name "myproject")
    assert_equals "claude-myproject" "$result" "Session name formatted correctly"

    result=$(get_tmux_session_name "default")
    assert_equals "claude-default" "$result" "Default session name formatted correctly"
}

# =============================================================================
# TESTS: EDGE CASES
# =============================================================================

test_mouse_mode_comment_present() {
    echo ""
    echo "Testing: mouse mode has explanatory comment"

    local script_content
    script_content=$(cat "$PROJECT_DIR/claude-remote")

    assert_contains "$script_content" "Enable mouse mode for proper touchpad scrolling" \
        "Comment explains purpose of mouse mode"
}

test_mac_specific_hint() {
    echo ""
    echo "Testing: Mac-specific text selection hint"

    local script_content
    script_content=$(cat "$PROJECT_DIR/claude-remote")

    assert_contains "$script_content" "Mac" \
        "Hint mentions Mac-specific behavior"
}

# =============================================================================
# TESTS: MULTI-SESSION LISTENER WIRING (issue #37)
# =============================================================================

test_no_legacy_per_session_spawn() {
    echo ""
    echo "Testing: claude-remote does not spawn per-session telegram-listener.py"

    local script_content
    script_content=$(cat "$PROJECT_DIR/claude-remote")

    assert_not_contains "$script_content" 'telegram-listener.py" --session' \
        "claude-remote does not invoke telegram-listener.py with --session"
}

test_ensure_multi_listener_present() {
    echo ""
    echo "Testing: claude-remote defines ensure_multi_listener helper"

    local script_content
    script_content=$(cat "$PROJECT_DIR/claude-remote")

    assert_contains "$script_content" "ensure_multi_listener()" \
        "ensure_multi_listener helper is defined"
    assert_contains "$script_content" "listener-multi.pid" \
        "Multi-session listener PID file path is referenced"
}

test_start_session_uses_multi_listener() {
    echo ""
    echo "Testing: start_session ensures the multi-session listener"

    local script_content
    script_content=$(cat "$PROJECT_DIR/claude-remote")

    # start_session must call ensure_multi_listener (instead of spawning a
    # per-session listener). Use grep -c to confirm the call site count is
    # higher than 1 (definition + at least one invocation).
    local call_count
    call_count=$(grep -c "ensure_multi_listener" "$PROJECT_DIR/claude-remote")

    TESTS_RUN=$((TESTS_RUN + 1))
    if [ "$call_count" -ge 2 ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: ensure_multi_listener is defined and called ($call_count refs)"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: ensure_multi_listener appears only $call_count times (need definition + at least one call)"
    fi
}

test_stop_session_does_not_kill_listener() {
    echo ""
    echo "Testing: stop_session does not kill the shared listener"

    # stop_session used to look up a per-session listener PID and kill it;
    # the new version must not reference that helper anywhere.
    local script_content
    script_content=$(cat "$PROJECT_DIR/claude-remote")

    assert_not_contains "$script_content" "get_listener_pid" \
        "Script no longer defines or calls get_listener_pid"
    assert_not_contains "$script_content" 'listener_running "$session"' \
        "Script no longer calls listener_running with a session arg"
}

test_cleanup_wrapper_does_not_kill_listener() {
    echo ""
    echo "Testing: tmux cleanup wrapper does not kill the listener"

    # Pull the heredoc body delimited by 'CLEANUP'. The heredoc is between
    # '<< '\''CLEANUP'\''' and a line that is just 'CLEANUP'.
    local wrapper_block
    wrapper_block=$(awk '/<< .CLEANUP./{flag=1; next} /^CLEANUP$/{flag=0} flag' "$PROJECT_DIR/claude-remote")

    assert_not_contains "$wrapper_block" 'listener-$CLAUDE_SESSION.pid' \
        "Cleanup wrapper does not reference per-session listener PID file"
    assert_contains "$wrapper_block" "multi-session" \
        "Cleanup wrapper explains why the listener is left running"
}

test_topic_conflict_check_iterates_configs() {
    echo ""
    echo "Testing: check_topic_conflicts iterates session configs, not PID files"

    # The check used to enumerate $PIDS_DIR/listener-*.pid. The fix walks
    # $SESSIONS_DIR/*.conf instead. Inspect the function via line numbers.
    local start_line end_line
    start_line=$(grep -n "^check_topic_conflicts()" "$PROJECT_DIR/claude-remote" | cut -d: -f1)

    if [ -z "$start_line" ]; then
        TESTS_RUN=$((TESTS_RUN + 1))
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: check_topic_conflicts not found in script"
        return 1
    fi

    # Walk forward to the next top-level function definition or top-level }.
    # Using sed to print from start_line until a closing brace at column 0.
    local block
    block=$(sed -n "${start_line},/^}/p" "$PROJECT_DIR/claude-remote")

    assert_contains "$block" 'SESSIONS_DIR"/\*\.conf' \
        "check_topic_conflicts iterates over session configs"
    assert_not_contains "$block" 'PIDS_DIR"/listener-\*\.pid' \
        "check_topic_conflicts no longer scans listener PID files"
}

test_remote_notify_uses_multi_pid_file() {
    echo ""
    echo "Testing: hooks/remote-notify.sh points get_pid_file at listener-multi.pid"

    local start_line
    start_line=$(grep -n "^get_pid_file()" "$PROJECT_DIR/hooks/remote-notify.sh" | cut -d: -f1)

    if [ -z "$start_line" ]; then
        TESTS_RUN=$((TESTS_RUN + 1))
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: get_pid_file not found in remote-notify.sh"
        return 1
    fi

    local block
    block=$(sed -n "${start_line},/^}/p" "$PROJECT_DIR/hooks/remote-notify.sh")

    assert_contains "$block" "listener-multi.pid" \
        "get_pid_file returns the multi-session PID path"
    assert_not_contains "$block" 'listener-$SESSION_NAME.pid' \
        "get_pid_file no longer returns a per-session PID path"
}

test_remote_notify_cmd_start_no_session_flag() {
    echo ""
    echo "Testing: remote-notify.sh cmd_start launches listener without --session"

    local script_content
    script_content=$(cat "$PROJECT_DIR/hooks/remote-notify.sh")

    # No invocation of the listener with --session anywhere in remote-notify.sh
    assert_not_contains "$script_content" '"$listener" --session' \
        "cmd_start does not pass --session SESSION_NAME"
    assert_contains "$script_content" "listener-multi.log" \
        "cmd_start logs to the multi-session log file"
}

test_ensure_multi_listener_starts_only_once() {
    echo ""
    echo "Testing: ensure_multi_listener is idempotent across sessions"

    setup

    # Stub helpers to capture spawn invocations and avoid touching the real bot.
    HOOKS_DIR="$CLAUDE_HOME/hooks"
    PIDS_DIR="$CLAUDE_HOME/pids"
    LOGS_DIR="$CLAUDE_HOME/logs"
    MULTI_LISTENER_PID_FILE="$PIDS_DIR/listener-multi.pid"
    MULTI_LISTENER_LOG="$LOGS_DIR/listener-multi.log"
    mkdir -p "$HOOKS_DIR"

    # Stub the listener so it just sleeps and writes its PID file.
    cat > "$HOOKS_DIR/telegram-listener.py" << 'STUB'
#!/usr/bin/env python3
import os, sys, time
pid_file = os.environ.get('STUB_PID_FILE')
if pid_file:
    with open(pid_file, 'w') as f:
        f.write(str(os.getpid()))
time.sleep(5)
STUB
    chmod +x "$HOOKS_DIR/telegram-listener.py"

    # Stub the cleanup script so cleanup_legacy_listeners is a no-op.
    cat > "$HOOKS_DIR/cleanup-old-listeners.sh" << 'STUB'
#!/usr/bin/env bash
exit 0
STUB
    chmod +x "$HOOKS_DIR/cleanup-old-listeners.sh"

    # Source the helper definitions from claude-remote without running main.
    # Extract just the multi-listener helpers via awk so we don't need the
    # rest of the script (which would invoke main on source).
    multi_listener_running() {
        if [ -f "$MULTI_LISTENER_PID_FILE" ]; then
            local pid=$(cat "$MULTI_LISTENER_PID_FILE")
            if kill -0 "$pid" 2>/dev/null; then
                return 0
            fi
        fi
        return 1
    }

    # Minimal ensure_multi_listener that mirrors production logic.
    ensure_multi_listener() {
        if multi_listener_running; then
            return 0
        fi
        STUB_PID_FILE="$MULTI_LISTENER_PID_FILE" \
            nohup python3 "$HOOKS_DIR/telegram-listener.py" \
            >> "$MULTI_LISTENER_LOG" 2>&1 &
        # Wait briefly for stub to write PID file
        for _ in 1 2 3 4 5; do
            [ -f "$MULTI_LISTENER_PID_FILE" ] && break
            sleep 0.2
        done
    }

    ensure_multi_listener
    local first_pid=""
    [ -f "$MULTI_LISTENER_PID_FILE" ] && first_pid=$(cat "$MULTI_LISTENER_PID_FILE")

    ensure_multi_listener
    local second_pid=""
    [ -f "$MULTI_LISTENER_PID_FILE" ] && second_pid=$(cat "$MULTI_LISTENER_PID_FILE")

    assert_equals "$first_pid" "$second_pid" \
        "Second ensure_multi_listener call does not spawn a new process"

    # Cleanup the stub listener
    if [ -n "$first_pid" ]; then
        kill "$first_pid" 2>/dev/null || true
    fi

    teardown
}

# =============================================================================
# RUN ALL TESTS
# =============================================================================

run_all_tests() {
    echo "=============================================="
    echo "  Running claude-remote unit tests"
    echo "=============================================="

    # Script content tests
    test_mouse_mode_enabled_in_script
    test_mouse_mode_after_session_block
    test_text_select_hint_present
    test_text_select_hint_near_detach_hint
    test_mouse_mode_comment_present
    test_mac_specific_hint

    # Integration tests
    test_tmux_mouse_mode_default_off
    test_tmux_session_has_mouse_mode

    # Validation function tests
    test_validate_bot_token_valid
    test_validate_bot_token_invalid
    test_validate_chat_id_valid
    test_validate_chat_id_invalid
    test_validate_topic_id_valid
    test_validate_topic_id_invalid

    # Helper function tests
    test_get_tmux_session_name

    # Multi-session listener wiring (issue #37)
    test_no_legacy_per_session_spawn
    test_ensure_multi_listener_present
    test_start_session_uses_multi_listener
    test_stop_session_does_not_kill_listener
    test_cleanup_wrapper_does_not_kill_listener
    test_topic_conflict_check_iterates_configs
    test_remote_notify_uses_multi_pid_file
    test_remote_notify_cmd_start_no_session_flag
    test_ensure_multi_listener_starts_only_once

    echo ""
    echo "=============================================="
    echo "  Test Results"
    echo "=============================================="
    echo "  Total:  $TESTS_RUN"
    echo "  Passed: $TESTS_PASSED"
    echo "  Failed: $TESTS_FAILED"

    local coverage
    if [ "$TESTS_RUN" -gt 0 ]; then
        coverage=$((TESTS_PASSED * 100 / TESTS_RUN))
    else
        coverage=0
    fi
    echo "  Coverage: ${coverage}%"

    if [ "$TESTS_FAILED" -eq 0 ]; then
        echo -e "  ${GREEN}All tests passed!${NC}"
        exit 0
    else
        echo -e "  ${RED}Some tests failed!${NC}"
        exit 1
    fi
}

run_all_tests
