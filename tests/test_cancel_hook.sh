#!/bin/bash
# =============================================================================
# test_cancel_hook.sh - Tests for cancel-pending-notification.sh
# =============================================================================

set -e

PASS=0
FAIL=0
TEST_DIR=$(mktemp -d -t "cancel-hook-test-XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CANCEL_SCRIPT="$SCRIPT_DIR/hooks/cancel-pending-notification.sh"

pass() {
    PASS=$((PASS + 1))
    echo "  ✓ $1"
}

fail() {
    FAIL=$((FAIL + 1))
    echo "  ✗ $1"
    [ -n "${2:-}" ] && echo "    $2"
}

echo "═══════════════════════════════════════════"
echo "  Cancel Pending Notification Hook Tests"
echo "═══════════════════════════════════════════"
echo ""

# -----------------------------------------------------------------------------
# Test: Script exists and is executable
# -----------------------------------------------------------------------------
echo "Script validation:"

if [ -x "$CANCEL_SCRIPT" ]; then
    pass "Script exists and is executable"
else
    fail "Script not found or not executable" "$CANCEL_SCRIPT"
fi

# -----------------------------------------------------------------------------
# Test: Exit 0 with no pending notification
# -----------------------------------------------------------------------------
echo ""
echo "No pending notification:"

MOCK_HOME="$TEST_DIR/claude-home"
mkdir -p "$MOCK_HOME/notifications-pending"

CLAUDE_HOME="$MOCK_HOME" CLAUDE_SESSION="test-session" bash "$CANCEL_SCRIPT" 2>/dev/null
EXIT_CODE=$?

if [ "$EXIT_CODE" -eq 0 ]; then
    pass "Exits 0 when no PID file exists"
else
    fail "Should exit 0 when no PID file" "exit code=$EXIT_CODE"
fi

# -----------------------------------------------------------------------------
# Test: Kills pending process via --session argument
# -----------------------------------------------------------------------------
echo ""
echo "Kill via --session argument:"

(sleep 30) &
BG_PID=$!
echo "$BG_PID" > "$MOCK_HOME/notifications-pending/my-session.pid"

CLAUDE_HOME="$MOCK_HOME" bash "$CANCEL_SCRIPT" --session my-session 2>/dev/null
EXIT_CODE=$?
sleep 0.1

if [ "$EXIT_CODE" -eq 0 ]; then
    pass "Exits 0 after cancel"
else
    fail "Should exit 0" "exit code=$EXIT_CODE"
fi

if [ ! -f "$MOCK_HOME/notifications-pending/my-session.pid" ]; then
    pass "PID file removed"
else
    fail "PID file should be removed"
fi

if ! kill -0 "$BG_PID" 2>/dev/null; then
    pass "Background process killed"
else
    fail "Background process should be killed"
    kill "$BG_PID" 2>/dev/null || true
fi

# -----------------------------------------------------------------------------
# Test: Uses CLAUDE_SESSION env var as fallback
# -----------------------------------------------------------------------------
echo ""
echo "CLAUDE_SESSION env var fallback:"

(sleep 30) &
BG_PID=$!
echo "$BG_PID" > "$MOCK_HOME/notifications-pending/env-session.pid"

CLAUDE_HOME="$MOCK_HOME" CLAUDE_SESSION="env-session" bash "$CANCEL_SCRIPT" 2>/dev/null
sleep 0.1

if [ ! -f "$MOCK_HOME/notifications-pending/env-session.pid" ]; then
    pass "PID file removed via CLAUDE_SESSION env var"
else
    fail "Should use CLAUDE_SESSION env var"
fi

if ! kill -0 "$BG_PID" 2>/dev/null; then
    pass "Process killed via CLAUDE_SESSION env var"
else
    fail "Process should be killed"
    kill "$BG_PID" 2>/dev/null || true
fi

# -----------------------------------------------------------------------------
# Test: --session flag overrides CLAUDE_SESSION
# -----------------------------------------------------------------------------
echo ""
echo "Flag overrides env var:"

(sleep 30) &
BG_PID=$!
echo "$BG_PID" > "$MOCK_HOME/notifications-pending/flag-session.pid"
echo "99999999" > "$MOCK_HOME/notifications-pending/env-session.pid"

CLAUDE_HOME="$MOCK_HOME" CLAUDE_SESSION="env-session" bash "$CANCEL_SCRIPT" --session flag-session 2>/dev/null
sleep 0.1

if [ ! -f "$MOCK_HOME/notifications-pending/flag-session.pid" ]; then
    pass "--session flag takes priority"
else
    fail "--session flag should take priority"
fi

# env-session PID file should still exist (untouched)
if [ -f "$MOCK_HOME/notifications-pending/env-session.pid" ]; then
    pass "Env var session PID file untouched"
else
    fail "Env var session PID file should be untouched"
fi

kill "$BG_PID" 2>/dev/null || true
rm -f "$MOCK_HOME/notifications-pending/env-session.pid"

# -----------------------------------------------------------------------------
# Test: Handles stale PID gracefully
# -----------------------------------------------------------------------------
echo ""
echo "Stale PID handling:"

echo "99999999" > "$MOCK_HOME/notifications-pending/stale-session.pid"

CLAUDE_HOME="$MOCK_HOME" bash "$CANCEL_SCRIPT" --session stale-session 2>/dev/null
EXIT_CODE=$?

if [ "$EXIT_CODE" -eq 0 ]; then
    pass "Exits 0 with stale PID"
else
    fail "Should exit 0 with stale PID"
fi

if [ ! -f "$MOCK_HOME/notifications-pending/stale-session.pid" ]; then
    pass "Stale PID file cleaned up"
else
    fail "Stale PID file should be removed"
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════"
TOTAL=$((PASS + FAIL))
echo "  Results: $PASS/$TOTAL passed"
if [ $FAIL -gt 0 ]; then
    echo "  $FAIL FAILED"
    echo "═══════════════════════════════════════════"
    exit 1
else
    echo "  All tests passed!"
    echo "═══════════════════════════════════════════"
    exit 0
fi
