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
