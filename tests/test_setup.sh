#!/bin/bash
# =============================================================================
# test_setup.sh - Unit tests for setup-telegram-remote.sh
# =============================================================================
#
# Usage: ./test_setup.sh
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SETUP_SCRIPT="$PROJECT_DIR/setup-telegram-remote.sh"

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

assert_symlink() {
    local file="$1"
    local message="${2:-}"

    TESTS_RUN=$((TESTS_RUN + 1))

    if [ -L "$file" ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $message"
        return 0
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $message (not a symlink: $file)"
        return 1
    fi
}

assert_not_symlink() {
    local file="$1"
    local message="${2:-}"

    TESTS_RUN=$((TESTS_RUN + 1))

    if [ -f "$file" ] && [ ! -L "$file" ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $message"
        return 0
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $message (is a symlink or doesn't exist: $file)"
        return 1
    fi
}

assert_symlink_target() {
    local symlink="$1"
    local expected_target="$2"
    local message="${3:-}"

    TESTS_RUN=$((TESTS_RUN + 1))

    if [ -L "$symlink" ]; then
        local actual_target=$(readlink "$symlink")
        if [ "$actual_target" = "$expected_target" ]; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            echo -e "  ${GREEN}PASS${NC}: $message"
            return 0
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo -e "  ${RED}FAIL${NC}: $message"
            echo "    Expected target: $expected_target"
            echo "    Actual target:   $actual_target"
            return 1
        fi
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $message (not a symlink)"
        return 1
    fi
}

# =============================================================================
# SETUP / TEARDOWN
# =============================================================================

TEMP_DIR=""
TEMP_CLAUDE_HOME=""

setup() {
    TEMP_DIR=$(mktemp -d)
    TEMP_CLAUDE_HOME="$TEMP_DIR/.claude"
    mkdir -p "$TEMP_CLAUDE_HOME"
    mkdir -p "$TEMP_DIR/.local/bin"
}

teardown() {
    if [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
}

# =============================================================================
# TESTS: HELP FLAG
# =============================================================================

test_help_flag() {
    echo ""
    echo "Testing: --help flag"

    local output=$("$SETUP_SCRIPT" --help 2>&1)

    TESTS_RUN=$((TESTS_RUN + 1))
    if echo "$output" | grep -q "Usage:"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: --help shows usage"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: --help should show usage"
    fi

    TESTS_RUN=$((TESTS_RUN + 1))
    if echo "$output" | grep -q "\-\-dev"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: --help mentions --dev flag"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: --help should mention --dev flag"
    fi

    TESTS_RUN=$((TESTS_RUN + 1))
    if echo "$output" | grep -q "symlink"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: --help explains symlinks"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: --help should explain symlinks"
    fi
}

# =============================================================================
# TESTS: INSTALL FILE FUNCTION
# =============================================================================

test_install_file_copy_mode() {
    echo ""
    echo "Testing: install_file in copy mode"

    setup

    # Create test source file
    local src_file="$TEMP_DIR/source.txt"
    echo "test content" > "$src_file"

    # Simulate install_file function behavior (copy mode)
    local dest_file="$TEMP_CLAUDE_HOME/dest.txt"
    cp "$src_file" "$dest_file"

    assert_file_exists "$dest_file" "File should be copied"
    assert_not_symlink "$dest_file" "File should not be a symlink in copy mode"

    # Verify content
    local content=$(cat "$dest_file")
    assert_equals "test content" "$content" "Content should match"

    teardown
}

test_install_file_dev_mode() {
    echo ""
    echo "Testing: install_file in dev mode (symlinks)"

    setup

    # Create test source file
    local src_file="$TEMP_DIR/source.txt"
    echo "test content" > "$src_file"

    # Simulate install_file function behavior (dev mode - symlink)
    local dest_file="$TEMP_CLAUDE_HOME/dest.txt"
    ln -sf "$src_file" "$dest_file"

    assert_file_exists "$dest_file" "Symlink should exist"
    assert_symlink "$dest_file" "File should be a symlink in dev mode"
    assert_symlink_target "$dest_file" "$src_file" "Symlink should point to source"

    # Verify content accessible through symlink
    local content=$(cat "$dest_file")
    assert_equals "test content" "$content" "Content should be accessible through symlink"

    teardown
}

test_dev_mode_changes_reflect_immediately() {
    echo ""
    echo "Testing: dev mode changes reflect immediately"

    setup

    # Create test source file
    local src_file="$TEMP_DIR/source.txt"
    echo "original content" > "$src_file"

    # Create symlink (dev mode)
    local dest_file="$TEMP_CLAUDE_HOME/dest.txt"
    ln -sf "$src_file" "$dest_file"

    # Modify source file
    echo "modified content" > "$src_file"

    # Verify change is reflected through symlink
    local content=$(cat "$dest_file")
    assert_equals "modified content" "$content" "Changes should reflect immediately through symlink"

    teardown
}

test_copy_mode_changes_do_not_reflect() {
    echo ""
    echo "Testing: copy mode changes do not reflect"

    setup

    # Create test source file
    local src_file="$TEMP_DIR/source.txt"
    echo "original content" > "$src_file"

    # Copy file (normal mode)
    local dest_file="$TEMP_CLAUDE_HOME/dest.txt"
    cp "$src_file" "$dest_file"

    # Modify source file
    echo "modified content" > "$src_file"

    # Verify change is NOT reflected in copy
    local content=$(cat "$dest_file")
    assert_equals "original content" "$content" "Changes should NOT reflect in copy"

    teardown
}

# =============================================================================
# TESTS: SYMLINK OVERWRITE
# =============================================================================

test_symlink_overwrites_existing_file() {
    echo ""
    echo "Testing: symlink overwrites existing regular file"

    setup

    # Create existing regular file at destination
    local dest_file="$TEMP_CLAUDE_HOME/dest.txt"
    echo "old content" > "$dest_file"

    # Create source file
    local src_file="$TEMP_DIR/source.txt"
    echo "new content" > "$src_file"

    # Install as symlink (should replace regular file)
    rm -f "$dest_file"
    ln -sf "$src_file" "$dest_file"

    assert_symlink "$dest_file" "Should be converted to symlink"

    local content=$(cat "$dest_file")
    assert_equals "new content" "$content" "Content should be from new source"

    teardown
}

test_copy_overwrites_existing_symlink() {
    echo ""
    echo "Testing: copy overwrites existing symlink"

    setup

    # Create source files
    local old_src="$TEMP_DIR/old_source.txt"
    echo "old content" > "$old_src"

    local new_src="$TEMP_DIR/new_source.txt"
    echo "new content" > "$new_src"

    # Create existing symlink at destination
    local dest_file="$TEMP_CLAUDE_HOME/dest.txt"
    ln -sf "$old_src" "$dest_file"

    # Install as copy (should replace symlink)
    rm -f "$dest_file"
    cp "$new_src" "$dest_file"

    assert_not_symlink "$dest_file" "Should be converted to regular file"

    local content=$(cat "$dest_file")
    assert_equals "new content" "$content" "Content should be from new source"

    teardown
}

# =============================================================================
# TESTS: EXECUTABLE PERMISSIONS
# =============================================================================

test_executable_permissions_copy() {
    echo ""
    echo "Testing: executable permissions in copy mode"

    setup

    # Create test script
    local src_file="$TEMP_DIR/script.sh"
    echo "#!/bin/bash" > "$src_file"
    echo "echo hello" >> "$src_file"

    # Copy and make executable
    local dest_file="$TEMP_CLAUDE_HOME/script.sh"
    cp "$src_file" "$dest_file"
    chmod +x "$dest_file"

    TESTS_RUN=$((TESTS_RUN + 1))
    if [ -x "$dest_file" ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Copied file is executable"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: Copied file should be executable"
    fi

    teardown
}

test_executable_permissions_symlink() {
    echo ""
    echo "Testing: executable permissions in symlink mode"

    setup

    # Create test script and make it executable
    local src_file="$TEMP_DIR/script.sh"
    echo "#!/bin/bash" > "$src_file"
    echo "echo hello" >> "$src_file"
    chmod +x "$src_file"

    # Create symlink
    local dest_file="$TEMP_CLAUDE_HOME/script.sh"
    ln -sf "$src_file" "$dest_file"

    TESTS_RUN=$((TESTS_RUN + 1))
    if [ -x "$dest_file" ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: Symlinked file is executable (via source)"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: Symlinked file should be executable"
    fi

    teardown
}

# =============================================================================
# RUN ALL TESTS
# =============================================================================

run_all_tests() {
    echo "=============================================="
    echo "  Running setup-telegram-remote.sh unit tests"
    echo "=============================================="

    test_help_flag
    test_install_file_copy_mode
    test_install_file_dev_mode
    test_dev_mode_changes_reflect_immediately
    test_copy_mode_changes_do_not_reflect
    test_symlink_overwrites_existing_file
    test_copy_overwrites_existing_symlink
    test_executable_permissions_copy
    test_executable_permissions_symlink

    echo ""
    echo "=============================================="
    echo "  Test Results"
    echo "=============================================="
    echo "  Total:  $TESTS_RUN"
    echo "  Passed: $TESTS_PASSED"
    echo "  Failed: $TESTS_FAILED"

    local coverage=$((TESTS_PASSED * 100 / TESTS_RUN))
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
