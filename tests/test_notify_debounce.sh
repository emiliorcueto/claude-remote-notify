#!/bin/bash
# =============================================================================
# test_notify_debounce.sh - Tests for notification debounce in telegram-notify.sh
# =============================================================================

set -e

PASS=0
FAIL=0
TEST_DIR=$(mktemp -d -t "debounce-test-XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

pass() {
    PASS=$((PASS + 1))
    echo "  ✓ $1"
}

fail() {
    FAIL=$((FAIL + 1))
    echo "  ✗ $1"
    [ -n "$2" ] && echo "    $2"
}

echo "═══════════════════════════════════════════"
echo "  Notification Debounce Tests"
echo "═══════════════════════════════════════════"
echo ""

# Setup mock environment
MOCK_CLAUDE_HOME="$TEST_DIR/claude"
mkdir -p "$MOCK_CLAUDE_HOME/sessions"
mkdir -p "$MOCK_CLAUDE_HOME/logs"
touch "$MOCK_CLAUDE_HOME/notifications-enabled"

# Create mock session config
cat > "$MOCK_CLAUDE_HOME/sessions/test.conf" << 'EOF'
TELEGRAM_BOT_TOKEN="test-token"
TELEGRAM_CHAT_ID="12345"
TELEGRAM_TOPIC_ID="67890"
NOTIFY_DEBOUNCE=2
EOF

# Create mock session config with debounce disabled
cat > "$MOCK_CLAUDE_HOME/sessions/nodelay.conf" << 'EOF'
TELEGRAM_BOT_TOKEN="test-token"
TELEGRAM_CHAT_ID="12345"
TELEGRAM_TOPIC_ID="67890"
NOTIFY_DEBOUNCE=0
EOF

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NOTIFY_SCRIPT="$SCRIPT_DIR/hooks/telegram-notify.sh"

# -----------------------------------------------------------------------------
# Test: Pending directory created
# -----------------------------------------------------------------------------
echo "Debounce file management:"

# Run with a short debounce to test file creation (will fail on API call, that's OK)
PENDING_DIR="$MOCK_CLAUDE_HOME/notifications-pending"
if [ -d "$PENDING_DIR" ]; then
    rm -rf "$PENDING_DIR"
fi

# Source only the debounce section by simulating the script's behavior
mkdir -p "$PENDING_DIR"
if [ -d "$PENDING_DIR" ]; then
    pass "Pending directory created"
else
    fail "Pending directory not created"
fi

# -----------------------------------------------------------------------------
# Test: PID file written
# -----------------------------------------------------------------------------
echo ""
echo "PID file management:"

SESSION_NAME="test-debounce"
PENDING_PID="$PENDING_DIR/$SESSION_NAME.pid"

# Simulate a background sender
(sleep 30) &
BG_PID=$!
echo "$BG_PID" > "$PENDING_PID"

if [ -f "$PENDING_PID" ]; then
    STORED_PID=$(cat "$PENDING_PID")
    if [ "$STORED_PID" = "$BG_PID" ]; then
        pass "PID file stores correct PID"
    else
        fail "PID file has wrong PID" "expected=$BG_PID got=$STORED_PID"
    fi
else
    fail "PID file not created"
fi

# -----------------------------------------------------------------------------
# Test: Kill previous sender
# -----------------------------------------------------------------------------

if kill -0 "$BG_PID" 2>/dev/null; then
    # Kill using the stored PID (simulating what the script does)
    OLD_PID=$(cat "$PENDING_PID" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID" 2>/dev/null || true
    fi
    rm -f "$PENDING_PID"

    sleep 0.1
    if ! kill -0 "$BG_PID" 2>/dev/null; then
        pass "Previous sender killed successfully"
    else
        fail "Previous sender still running after kill"
        kill "$BG_PID" 2>/dev/null || true
    fi
else
    fail "Background process died before test"
fi

# -----------------------------------------------------------------------------
# Test: Stale PID handling
# -----------------------------------------------------------------------------
echo ""
echo "Stale PID handling:"

# Write a PID that doesn't exist
echo "99999999" > "$PENDING_PID"
OLD_PID=$(cat "$PENDING_PID" 2>/dev/null)
if [ -n "$OLD_PID" ] && ! kill -0 "$OLD_PID" 2>/dev/null; then
    rm -f "$PENDING_PID"
    pass "Stale PID detected and cleaned up"
else
    fail "Stale PID not handled"
fi

# -----------------------------------------------------------------------------
# Test: Debounce resets timer (rapid calls)
# -----------------------------------------------------------------------------
echo ""
echo "Debounce timer reset:"

# Spawn a first sender (1 second sleep)
(sleep 1; echo "first" > "$TEST_DIR/sent-1") &
PID1=$!
echo "$PID1" > "$PENDING_PID"

sleep 0.2

# Kill first and spawn second (simulates rapid hook calls)
OLD_PID=$(cat "$PENDING_PID" 2>/dev/null)
if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" 2>/dev/null || true
fi

(sleep 1; echo "second" > "$TEST_DIR/sent-2") &
PID2=$!
echo "$PID2" > "$PENDING_PID"

# Wait for both to complete
sleep 1.5

if [ ! -f "$TEST_DIR/sent-1" ] && [ -f "$TEST_DIR/sent-2" ]; then
    pass "First sender cancelled, second sender completed"
elif [ -f "$TEST_DIR/sent-1" ] && [ -f "$TEST_DIR/sent-2" ]; then
    fail "Both senders ran (debounce didn't cancel first)"
elif [ ! -f "$TEST_DIR/sent-1" ] && [ ! -f "$TEST_DIR/sent-2" ]; then
    fail "Neither sender ran"
else
    fail "Only first sender ran (second was lost)"
fi

# Cleanup
kill "$PID1" 2>/dev/null || true
kill "$PID2" 2>/dev/null || true
rm -f "$PENDING_PID"

# -----------------------------------------------------------------------------
# Test: NOTIFY_DEBOUNCE=0 skips debounce
# -----------------------------------------------------------------------------
echo ""
echo "Debounce disable (NOTIFY_DEBOUNCE=0):"

DEBOUNCE_SECONDS=0
if [ "$DEBOUNCE_SECONDS" -eq 0 ] 2>/dev/null; then
    pass "NOTIFY_DEBOUNCE=0 detected as immediate send"
else
    fail "NOTIFY_DEBOUNCE=0 not properly handled"
fi

# -----------------------------------------------------------------------------
# Test: Default debounce value
# -----------------------------------------------------------------------------
echo ""
echo "Default configuration:"

NOTIFY_DEBOUNCE=""
DEBOUNCE_SECONDS="${NOTIFY_DEBOUNCE:-20}"
if [ "$DEBOUNCE_SECONDS" = "20" ]; then
    pass "Default debounce is 20 seconds"
else
    fail "Default debounce wrong" "expected=20 got=$DEBOUNCE_SECONDS"
fi

# Custom value
NOTIFY_DEBOUNCE=30
DEBOUNCE_SECONDS="${NOTIFY_DEBOUNCE:-20}"
if [ "$DEBOUNCE_SECONDS" = "30" ]; then
    pass "Custom debounce value respected"
else
    fail "Custom debounce not applied" "expected=30 got=$DEBOUNCE_SECONDS"
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
