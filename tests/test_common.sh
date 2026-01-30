#!/bin/bash
# =============================================================================
# test_common.sh - Unit tests for lib/common.sh
# =============================================================================
#
# Usage: ./test_common.sh
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LIB_DIR="$PROJECT_DIR/lib"

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

assert_not_empty() {
    local value="$1"
    local message="${2:-}"

    TESTS_RUN=$((TESTS_RUN + 1))

    if [ -n "$value" ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $message"
        return 0
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $message (value was empty)"
        return 1
    fi
}

assert_file_exists() {
    local file="$1"
    local message="${2:-}"

    TESTS_RUN=$((TESTS_RUN + 1))

    if [ -f "$file" ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $message"
        return 0
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $message (file not found: $file)"
        return 1
    fi
}

assert_command_fails() {
    local message="$1"
    shift

    TESTS_RUN=$((TESTS_RUN + 1))

    if "$@" 2>/dev/null; then
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $message (command should have failed)"
        return 1
    else
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $message"
        return 0
    fi
}

# =============================================================================
# SETUP / TEARDOWN
# =============================================================================

TEMP_DIR=""

setup() {
    TEMP_DIR=$(mktemp -d)
    # Source the library in a subshell for each test
}

teardown() {
    if [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
}

# =============================================================================
# TESTS: TEMP FILE HANDLING
# =============================================================================

test_create_temp_file() {
    echo ""
    echo "Testing: create_temp_file"

    # Source in current shell context for cleanup test
    source "$LIB_DIR/common.sh"

    local temp_file
    temp_file=$(create_temp_file "test-prefix" ".txt")
    _COMMON_TEMP_FILES+=("$temp_file")

    assert_file_exists "$temp_file" "Temp file should be created"
    assert_not_empty "$(echo "$temp_file" | grep 'test-prefix')" "Temp file should contain prefix"
    assert_not_empty "$(echo "$temp_file" | grep '.txt')" "Temp file should have suffix"

    # Cleanup should work
    cleanup_temp_files
    TESTS_RUN=$((TESTS_RUN + 1))
    if [ ! -f "$temp_file" ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Temp file cleaned up successfully"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: Temp file should be cleaned up"
        rm -f "$temp_file"
    fi
}

test_create_temp_dir() {
    echo ""
    echo "Testing: create_temp_dir"

    # Source in current shell context for cleanup test
    source "$LIB_DIR/common.sh"

    local temp_dir
    temp_dir=$(create_temp_dir "test-dir")
    _COMMON_TEMP_FILES+=("$temp_dir")

    TESTS_RUN=$((TESTS_RUN + 1))
    if [ -d "$temp_dir" ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Temp directory should be created"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: Temp directory not created"
    fi

    # Cleanup
    cleanup_temp_files
    TESTS_RUN=$((TESTS_RUN + 1))
    if [ ! -d "$temp_dir" ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Temp directory cleaned up"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: Temp directory not cleaned up"
        rm -rf "$temp_dir"
    fi
}

# =============================================================================
# TESTS: SAFE VARIABLE SUBSTITUTION
# =============================================================================

test_safe_substitute() {
    echo ""
    echo "Testing: safe_substitute"

    setup

    local test_file="$TEMP_DIR/test.txt"
    echo "Hello PLACEHOLDER world" > "$test_file"

    (
        source "$LIB_DIR/common.sh"

        safe_substitute "$test_file" "PLACEHOLDER" "Claude"

        local content
        content=$(cat "$test_file")
        assert_equals "Hello Claude world" "$content" "Placeholder should be replaced"
    )

    teardown
}

test_safe_substitute_with_special_chars() {
    echo ""
    echo "Testing: safe_substitute with special characters"

    setup

    local test_file="$TEMP_DIR/test.txt"
    echo "Session: SESSION_PLACEHOLDER" > "$test_file"

    (
        source "$LIB_DIR/common.sh"

        # Test with value containing special regex chars
        safe_substitute "$test_file" "SESSION_PLACEHOLDER" "my-session_123"

        local content
        content=$(cat "$test_file")
        assert_equals "Session: my-session_123" "$content" "Special chars should be handled"
    )

    teardown
}

test_safe_substitute_multi() {
    echo ""
    echo "Testing: safe_substitute_multi"

    setup

    local test_file="$TEMP_DIR/test.txt"
    cat > "$test_file" << 'EOF'
Session: SESSION_PLACEHOLDER
Tmux: TMUX_PLACEHOLDER
EOF

    (
        source "$LIB_DIR/common.sh"

        safe_substitute_multi "$test_file" \
            "SESSION_PLACEHOLDER=mysession" \
            "TMUX_PLACEHOLDER=claude-mysession"

        local content
        content=$(cat "$test_file")

        TESTS_RUN=$((TESTS_RUN + 1))
        if echo "$content" | grep -q "Session: mysession"; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: First placeholder replaced"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: First placeholder not replaced"
        fi

        TESTS_RUN=$((TESTS_RUN + 1))
        if echo "$content" | grep -q "Tmux: claude-mysession"; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: Second placeholder replaced"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: Second placeholder not replaced"
        fi
    )

    teardown
}

# =============================================================================
# TESTS: INPUT VALIDATION
# =============================================================================

test_validate_session_name() {
    echo ""
    echo "Testing: validate_session_name"

    (
        source "$LIB_DIR/common.sh"

        # Valid names
        local result
        result=$(validate_session_name "myproject")
        assert_equals "myproject" "$result" "Valid alphanumeric name accepted"

        result=$(validate_session_name "my-project")
        assert_equals "my-project" "$result" "Dash in name accepted"

        result=$(validate_session_name "my_project")
        assert_equals "my_project" "$result" "Underscore in name accepted"

        result=$(validate_session_name "Project123")
        assert_equals "Project123" "$result" "Mixed case with numbers accepted"
    )

    # Invalid names (should fail)
    (
        source "$LIB_DIR/common.sh" 2>/dev/null || true

        assert_command_fails "Name with spaces rejected" validate_session_name "my project"
        assert_command_fails "Name with semicolon rejected" validate_session_name "my;project"
        assert_command_fails "Name with shell chars rejected" validate_session_name 'my$(whoami)'
    )
}

test_sanitize_input() {
    echo ""
    echo "Testing: sanitize_input"

    (
        source "$LIB_DIR/common.sh"

        local result

        result=$(sanitize_input "hello world")
        assert_equals "hello world" "$result" "Normal text unchanged"

        result=$(sanitize_input "hello; rm -rf /")
        assert_equals "hello rm -rf /" "$result" "Semicolon removed"

        result=$(sanitize_input 'hello$(whoami)')
        assert_equals "hellowhoami" "$result" "Command substitution chars removed"

        result=$(sanitize_input "file.txt")
        assert_equals "file.txt" "$result" "Dots preserved"

        result=$(sanitize_input "path/to/file")
        assert_equals "path/to/file" "$result" "Slashes preserved"
    )
}

test_validate_path_in_dir() {
    echo ""
    echo "Testing: validate_path_in_dir"

    setup

    mkdir -p "$TEMP_DIR/base/subdir"
    echo "test" > "$TEMP_DIR/base/subdir/file.txt"
    echo "outside" > "$TEMP_DIR/outside.txt"

    (
        source "$LIB_DIR/common.sh"

        # Valid path
        local result
        result=$(validate_path_in_dir "$TEMP_DIR/base/subdir/file.txt" "$TEMP_DIR/base")
        assert_not_empty "$result" "Valid path in dir accepted"

        # Invalid path (outside base)
        assert_command_fails "Path outside base rejected" \
            validate_path_in_dir "$TEMP_DIR/outside.txt" "$TEMP_DIR/base"
    )

    teardown
}

# =============================================================================
# TESTS: SCRIPT VALIDATION
# =============================================================================

test_validate_script() {
    echo ""
    echo "Testing: validate_script"

    setup

    # Create valid script
    local valid_script="$TEMP_DIR/valid.sh"
    echo '#!/bin/bash' > "$valid_script"
    echo 'echo hello' >> "$valid_script"
    chmod 755 "$valid_script"

    # Create world-writable script
    local unsafe_script="$TEMP_DIR/unsafe.sh"
    echo '#!/bin/bash' > "$unsafe_script"
    chmod 777 "$unsafe_script"

    (
        source "$LIB_DIR/common.sh"

        # Valid script should pass
        local result
        result=$(validate_script "$valid_script")
        assert_equals "$valid_script" "$result" "Valid script accepted"

        # Non-existent script should fail
        assert_command_fails "Non-existent script rejected" \
            validate_script "$TEMP_DIR/nonexistent.sh"

        # Directory should fail
        assert_command_fails "Directory rejected" \
            validate_script "$TEMP_DIR"
    )

    teardown
}

# =============================================================================
# TESTS: LOGGING
# =============================================================================

test_logging_functions() {
    echo ""
    echo "Testing: logging functions"

    (
        source "$LIB_DIR/common.sh"

        # Just ensure they don't crash
        log_debug "Debug message" 2>/dev/null
        log_info "Info message" 2>/dev/null
        log_warn "Warning message" 2>/dev/null
        log_error "Error message" 2>/dev/null

        TESTS_RUN=$((TESTS_RUN + 1))
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Logging functions execute without error"
    )
}

# =============================================================================
# TESTS: SAFE CONFIG LOADING
# =============================================================================

test_load_config_safely() {
    echo ""
    echo "Testing: load_config_safely"

    setup

    # Create a valid config file
    local config_file="$TEMP_DIR/test.conf"
    cat > "$config_file" << 'EOF'
# Test config
TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz123456789"
TELEGRAM_CHAT_ID="-1001234567890"
TELEGRAM_TOPIC_ID="123"
TMUX_SESSION="claude-test"
# Invalid key should be ignored
MALICIOUS_VAR="should-not-load"
EOF
    chmod 600 "$config_file"

    (
        source "$LIB_DIR/common.sh"

        # Load config
        load_config_safely "$config_file"

        # Check whitelisted vars loaded
        assert_not_empty "$TELEGRAM_BOT_TOKEN" "Bot token should be loaded"
        assert_not_empty "$TELEGRAM_CHAT_ID" "Chat ID should be loaded"
        assert_equals "123" "$TELEGRAM_TOPIC_ID" "Topic ID should be loaded"
        assert_equals "claude-test" "$TMUX_SESSION" "tmux session should be loaded"

        # Check non-whitelisted var not loaded
        TESTS_RUN=$((TESTS_RUN + 1))
        if [ -z "${MALICIOUS_VAR:-}" ]; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: Non-whitelisted var not loaded"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: Non-whitelisted var should not be loaded"
        fi
    )

    teardown
}

test_load_config_safely_rejects_world_writable() {
    echo ""
    echo "Testing: load_config_safely rejects world-writable"

    setup

    local config_file="$TEMP_DIR/unsafe.conf"
    echo 'TELEGRAM_BOT_TOKEN="test"' > "$config_file"
    chmod 666 "$config_file"

    (
        source "$LIB_DIR/common.sh"

        assert_command_fails "World-writable config rejected" \
            load_config_safely "$config_file"
    )

    teardown
}

# =============================================================================
# TESTS: TELEGRAM VALIDATION
# =============================================================================

test_validate_bot_token() {
    echo ""
    echo "Testing: validate_bot_token"

    (
        source "$LIB_DIR/common.sh"

        # Valid tokens
        TESTS_RUN=$((TESTS_RUN + 1))
        if validate_bot_token "123456789:ABCdefGHIjklMNOpqrsTUVwxyz123456789"; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: Valid token accepted"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: Valid token should be accepted"
        fi

        # Invalid tokens
        assert_command_fails "Token without colon rejected" validate_bot_token "123456789ABCdef"
        assert_command_fails "Token with short ID rejected" validate_bot_token "123:ABCdefGHIjklMNOpqrsTUVwxyz123456"
        assert_command_fails "Empty token rejected" validate_bot_token ""
    )
}

test_validate_chat_id() {
    echo ""
    echo "Testing: validate_chat_id"

    (
        source "$LIB_DIR/common.sh"

        # Valid chat IDs
        TESTS_RUN=$((TESTS_RUN + 1))
        if validate_chat_id "-1001234567890"; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: Valid negative group ID accepted"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: Valid negative group ID should be accepted"
        fi

        TESTS_RUN=$((TESTS_RUN + 1))
        if validate_chat_id "123456789"; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: Valid positive user ID accepted"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: Valid positive user ID should be accepted"
        fi

        # Invalid chat IDs
        assert_command_fails "Chat ID with letters rejected" validate_chat_id "abc123"
        assert_command_fails "Chat ID with spaces rejected" validate_chat_id "123 456"
    )
}

test_validate_topic_id() {
    echo ""
    echo "Testing: validate_topic_id"

    (
        source "$LIB_DIR/common.sh"

        # Valid topic IDs
        TESTS_RUN=$((TESTS_RUN + 1))
        if validate_topic_id "123"; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: Valid topic ID accepted"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: Valid topic ID should be accepted"
        fi

        TESTS_RUN=$((TESTS_RUN + 1))
        if validate_topic_id ""; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: Empty topic ID accepted"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: Empty topic ID should be accepted"
        fi

        # Invalid topic IDs
        assert_command_fails "Negative topic ID rejected" validate_topic_id "-123"
        assert_command_fails "Topic ID with letters rejected" validate_topic_id "abc"
    )
}

# =============================================================================
# TESTS: SESSION IDENTIFIER RESOLUTION
# =============================================================================

test_resolve_by_name() {
    echo ""
    echo "Testing: resolve_session_identifier by name"

    setup
    mkdir -p "$TEMP_DIR/sessions"
    cat > "$TEMP_DIR/sessions/myproject.conf" << 'EOF'
TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz123456789"
TELEGRAM_CHAT_ID="-1001234567890"
TELEGRAM_TOPIC_ID="70"
TMUX_SESSION="claude-myproject"
EOF

    (
        source "$LIB_DIR/common.sh"

        local result
        result=$(resolve_session_identifier "myproject" "$TEMP_DIR/sessions")
        assert_equals "myproject" "$result" "Session name resolves to itself"
    )
    teardown
}

test_resolve_by_topic_id() {
    echo ""
    echo "Testing: resolve_session_identifier by topic ID"

    setup
    mkdir -p "$TEMP_DIR/sessions"
    cat > "$TEMP_DIR/sessions/myproject.conf" << 'EOF'
TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz123456789"
TELEGRAM_CHAT_ID="-1001234567890"
TELEGRAM_TOPIC_ID="70"
TMUX_SESSION="claude-myproject"
EOF

    (
        source "$LIB_DIR/common.sh"

        local result
        result=$(resolve_session_identifier "70" "$TEMP_DIR/sessions")
        assert_equals "myproject" "$result" "Topic ID 70 resolves to myproject"
    )
    teardown
}

test_resolve_name_priority() {
    echo ""
    echo "Testing: resolve_session_identifier name takes priority over topic ID"

    setup
    mkdir -p "$TEMP_DIR/sessions"
    # Session literally named "70"
    cat > "$TEMP_DIR/sessions/70.conf" << 'EOF'
TELEGRAM_TOPIC_ID="999"
EOF
    # Another session with topic_id=70
    cat > "$TEMP_DIR/sessions/other.conf" << 'EOF'
TELEGRAM_TOPIC_ID="70"
EOF

    (
        source "$LIB_DIR/common.sh"

        local result
        result=$(resolve_session_identifier "70" "$TEMP_DIR/sessions")
        assert_equals "70" "$result" "Session name '70' wins over topic_id=70"
    )
    teardown
}

test_resolve_topic_not_found() {
    echo ""
    echo "Testing: resolve_session_identifier topic ID not found"

    setup
    mkdir -p "$TEMP_DIR/sessions"
    cat > "$TEMP_DIR/sessions/myproject.conf" << 'EOF'
TELEGRAM_TOPIC_ID="70"
EOF

    (
        source "$LIB_DIR/common.sh"

        assert_command_fails "Unknown topic ID rejected" \
            resolve_session_identifier "999" "$TEMP_DIR/sessions"
    )
    teardown
}

test_resolve_topic_duplicate() {
    echo ""
    echo "Testing: resolve_session_identifier duplicate topic ID"

    setup
    mkdir -p "$TEMP_DIR/sessions"
    cat > "$TEMP_DIR/sessions/session1.conf" << 'EOF'
TELEGRAM_TOPIC_ID="70"
EOF
    cat > "$TEMP_DIR/sessions/session2.conf" << 'EOF'
TELEGRAM_TOPIC_ID="70"
EOF

    (
        source "$LIB_DIR/common.sh"

        assert_command_fails "Duplicate topic ID rejected" \
            resolve_session_identifier "70" "$TEMP_DIR/sessions"
    )
    teardown
}

test_resolve_nonexistent_passthrough() {
    echo ""
    echo "Testing: resolve_session_identifier non-numeric unknown passes through"

    setup
    mkdir -p "$TEMP_DIR/sessions"

    (
        source "$LIB_DIR/common.sh"

        local result
        result=$(resolve_session_identifier "nonexistent" "$TEMP_DIR/sessions")
        assert_equals "nonexistent" "$result" "Non-numeric name passes through"
    )
    teardown
}

# =============================================================================
# TESTS: SENSITIVE DATA MASKING
# =============================================================================

test_mask_sensitive() {
    echo ""
    echo "Testing: mask_sensitive"

    (
        source "$LIB_DIR/common.sh"

        local result

        result=$(mask_sensitive "1234567890abcdefghij" 3 2)
        assert_equals "123...ij" "$result" "Long string masked correctly"

        result=$(mask_sensitive "short" 3 2)
        assert_equals "***" "$result" "Short string fully masked"

        result=$(mask_sensitive "" 3 2)
        assert_equals "***" "$result" "Empty string masked"
    )
}

# =============================================================================
# TESTS: URL ENCODING
# =============================================================================

test_urlencode_shell() {
    echo ""
    echo "Testing: urlencode_shell"

    (
        source "$LIB_DIR/common.sh"

        local result

        # Basic alphanumeric (should be unchanged)
        result=$(urlencode_shell "hello123")
        assert_equals "hello123" "$result" "Alphanumeric unchanged"

        # Space should be encoded
        result=$(urlencode_shell "hello world")
        assert_equals "hello%20world" "$result" "Space encoded"

        # Special characters
        result=$(urlencode_shell "a=b&c=d")
        assert_equals "a%3Db%26c%3Dd" "$result" "Special chars encoded"

        # Safe characters (should not be encoded)
        result=$(urlencode_shell "hello-world_test.txt")
        assert_equals "hello-world_test.txt" "$result" "Safe chars unchanged"

        # Empty string
        result=$(urlencode_shell "")
        assert_equals "" "$result" "Empty string unchanged"
    )
}

test_urlencode_python() {
    echo ""
    echo "Testing: urlencode (python)"

    (
        source "$LIB_DIR/common.sh"

        local result

        # Basic test
        result=$(urlencode "hello world")
        assert_equals "hello%20world" "$result" "Space encoded with python"

        # Special characters
        result=$(urlencode "a=b&c=d")
        assert_equals "a%3Db%26c%3Dd" "$result" "Special chars encoded with python"
    )
}

# =============================================================================
# TESTS: TELEGRAM FORMATTING
# =============================================================================

test_format_for_telegram_strips_ansi() {
    echo ""
    echo "Testing: format_for_telegram strips ANSI codes"

    (
        source "$LIB_DIR/common.sh"

        local input result

        # Red text ANSI code
        input=$'\x1b[31mRed text\x1b[0m'
        result=$(format_for_telegram "$input")
        assert_equals "Red text" "$result" "ANSI color codes stripped"

        # Bold ANSI code
        input=$'\x1b[1mBold text\x1b[0m'
        result=$(format_for_telegram "$input")
        assert_equals "Bold text" "$result" "ANSI bold codes stripped"

        # Multiple ANSI codes
        input=$'\x1b[1;31;40mStyled text\x1b[0m normal'
        result=$(format_for_telegram "$input")
        assert_equals "Styled text normal" "$result" "Multiple ANSI codes stripped"
    )
}

test_format_for_telegram_converts_ascii_table() {
    echo ""
    echo "Testing: format_for_telegram converts ASCII tables"

    (
        source "$LIB_DIR/common.sh"

        local input result

        # Simple ASCII table with pipe separators
        input="| Issue | Status |
|-------|--------|
| #2 Fix | Closed |"
        result=$(format_for_telegram "$input")

        TESTS_RUN=$((TESTS_RUN + 1))
        if echo "$result" | grep -q "• #2 Fix — Closed"; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: ASCII table converted to bullet point"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: ASCII table should convert to bullet point"
            echo "    Got: $result"
        fi
    )
}

test_format_for_telegram_converts_unicode_table() {
    echo ""
    echo "Testing: format_for_telegram converts Unicode tables"

    (
        source "$LIB_DIR/common.sh"

        local input result

        # Unicode box-drawing table
        input="┌─────────────────────┬──────────┐
│ Issue               │ Status   │
├─────────────────────┼──────────┤
│ #2 Critical fixes   │ Closed ✓ │
└─────────────────────┴──────────┘"
        result=$(format_for_telegram "$input")

        TESTS_RUN=$((TESTS_RUN + 1))
        if echo "$result" | grep -q "• #2 Critical fixes — Closed ✓"; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: Unicode table converted to bullet point"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: Unicode table should convert to bullet point"
            echo "    Got: $result"
        fi
    )
}

test_format_for_telegram_preserves_normal_text() {
    echo ""
    echo "Testing: format_for_telegram preserves normal text"

    (
        source "$LIB_DIR/common.sh"

        local input result

        input="Hello world
This is normal text
With multiple lines"
        result=$(format_for_telegram "$input")

        TESTS_RUN=$((TESTS_RUN + 1))
        if [ "$result" = "$input" ]; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: Normal text preserved"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: Normal text should be preserved"
            echo "    Expected: $input"
            echo "    Got: $result"
        fi
    )
}

test_format_for_telegram_handles_mixed_content() {
    echo ""
    echo "Testing: format_for_telegram handles mixed content"

    (
        source "$LIB_DIR/common.sh"

        local input result

        # Mix of normal text and table
        input="Status report:
| Task | Done |
|------|------|
| Test | Yes  |
End of report"
        result=$(format_for_telegram "$input")

        TESTS_RUN=$((TESTS_RUN + 1))
        if echo "$result" | grep -q "Status report:" && echo "$result" | grep -q "• Test — Yes" && echo "$result" | grep -q "End of report"; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: Mixed content handled correctly"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: Mixed content should preserve text and convert table"
            echo "    Got: $result"
        fi
    )
}

test_format_for_telegram_handles_single_column_table() {
    echo ""
    echo "Testing: format_for_telegram handles single column table"

    (
        source "$LIB_DIR/common.sh"

        local input result

        input="| Items |
|-------|
| One   |
| Two   |"
        result=$(format_for_telegram "$input")

        TESTS_RUN=$((TESTS_RUN + 1))
        if echo "$result" | grep -q "• One" && echo "$result" | grep -q "• Two"; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: Single column table converted"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: Single column table should convert to bullets"
            echo "    Got: $result"
        fi
    )
}

test_format_for_telegram_handles_multi_column_table() {
    echo ""
    echo "Testing: format_for_telegram handles multi-column table"

    (
        source "$LIB_DIR/common.sh"

        local input result

        input="| Col1 | Col2 | Col3 |
|------|------|------|
| A    | B    | C    |"
        result=$(format_for_telegram "$input")

        TESTS_RUN=$((TESTS_RUN + 1))
        if echo "$result" | grep -q "• A — B — C"; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: Multi-column table converted with em-dashes"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: Multi-column table should join with em-dashes"
            echo "    Got: $result"
        fi
    )
}

test_format_for_telegram_empty_input() {
    echo ""
    echo "Testing: format_for_telegram handles empty input"

    (
        source "$LIB_DIR/common.sh"

        local result
        result=$(format_for_telegram "")

        TESTS_RUN=$((TESTS_RUN + 1))
        if [ -z "$result" ]; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: Empty input returns empty output"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: Empty input should return empty"
        fi
    )
}

test_format_for_telegram_border_only_lines_removed() {
    echo ""
    echo "Testing: format_for_telegram removes border-only lines"

    (
        source "$LIB_DIR/common.sh"

        local input result

        # Lines with only box characters should not appear in output
        input="━━━━━━━━━━━━━━━━━━━━━━
Some text
━━━━━━━━━━━━━━━━━━━━━━"
        result=$(format_for_telegram "$input")

        TESTS_RUN=$((TESTS_RUN + 1))
        if echo "$result" | grep -q "Some text" && ! echo "$result" | grep -q "━━━"; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: Border-only lines removed"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: Border-only lines should be removed"
            echo "    Got: $result"
        fi
    )
}

test_format_for_telegram_preserves_markdown() {
    echo ""
    echo "Testing: format_for_telegram preserves markdown formatting"

    (
        source "$LIB_DIR/common.sh"

        local input result

        input="This has **bold** and *italic* and \`code\` formatting"
        result=$(format_for_telegram "$input")

        TESTS_RUN=$((TESTS_RUN + 1))
        if [ "$result" = "$input" ]; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: Markdown formatting preserved"
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: Markdown formatting should be preserved"
            echo "    Expected: $input"
            echo "    Got: $result"
        fi
    )
}

# =============================================================================
# RUN ALL TESTS
# =============================================================================

run_all_tests() {
    echo "=============================================="
    echo "  Running lib/common.sh unit tests"
    echo "=============================================="

    test_create_temp_file
    test_create_temp_dir
    test_safe_substitute
    test_safe_substitute_with_special_chars
    test_safe_substitute_multi
    test_validate_session_name
    test_sanitize_input
    test_validate_path_in_dir
    test_validate_script
    test_logging_functions
    test_load_config_safely
    test_load_config_safely_rejects_world_writable
    test_validate_bot_token
    test_validate_chat_id
    test_validate_topic_id
    test_resolve_by_name
    test_resolve_by_topic_id
    test_resolve_name_priority
    test_resolve_topic_not_found
    test_resolve_topic_duplicate
    test_resolve_nonexistent_passthrough
    test_mask_sensitive
    test_urlencode_shell
    test_urlencode_python
    test_format_for_telegram_strips_ansi
    test_format_for_telegram_converts_ascii_table
    test_format_for_telegram_converts_unicode_table
    test_format_for_telegram_preserves_normal_text
    test_format_for_telegram_handles_mixed_content
    test_format_for_telegram_handles_single_column_table
    test_format_for_telegram_handles_multi_column_table
    test_format_for_telegram_empty_input
    test_format_for_telegram_border_only_lines_removed
    test_format_for_telegram_preserves_markdown

    echo ""
    echo "=============================================="
    echo "  Test Results"
    echo "=============================================="
    echo "  Total:  $TESTS_RUN"
    echo "  Passed: $TESTS_PASSED"
    echo "  Failed: $TESTS_FAILED"

    if [ "$TESTS_FAILED" -eq 0 ]; then
        echo -e "  ${GREEN}All tests passed!${NC}"
        exit 0
    else
        echo -e "  ${RED}Some tests failed!${NC}"
        exit 1
    fi
}

run_all_tests
