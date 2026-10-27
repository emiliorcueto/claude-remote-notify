#!/bin/bash
# =============================================================================
# test_preview_script.sh - Tests for line-count handling in telegram-preview.sh
# =============================================================================
#
# Runs hooks/telegram-preview.sh end-to-end against fake `tmux` and `curl`
# binaries on PATH. The fake tmux returns a fixture pane; the fake curl
# records the caption and a copy of the uploaded HTML document.
#
# =============================================================================

set -e

PASS=0
FAIL=0
TEST_DIR=$(mktemp -d -t "preview-test-XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

pass() {
    PASS=$((PASS + 1))
    echo "  ✓ $1"
}

fail() {
    FAIL=$((FAIL + 1))
    echo "  ✗ $1"
    if [ -n "$2" ]; then
        echo "    $2"
    fi
}

echo "═══════════════════════════════════════════"
echo "  Preview Script Tests"
echo "═══════════════════════════════════════════"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PREVIEW_SCRIPT="$SCRIPT_DIR/hooks/telegram-preview.sh"

if ! python3 -c "import ansi2html" 2>/dev/null; then
    echo "  ⚠ ansi2html not installed - skipping (pip install --user ansi2html)"
    exit 0
fi

# Mock environment
MOCK_CLAUDE_HOME="$TEST_DIR/claude"
mkdir -p "$MOCK_CLAUDE_HOME/sessions"
cat > "$MOCK_CLAUDE_HOME/sessions/test.conf" << 'EOF'
TELEGRAM_BOT_TOKEN="test-token"
TELEGRAM_CHAT_ID="12345"
TELEGRAM_TOPIC_ID="67890"
EOF

# Fake binaries
BIN_DIR="$TEST_DIR/bin"
mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/tmux" << 'EOF'
#!/bin/bash
case "$1" in
    has-session) exit 0 ;;
    capture-pane) cat "$FAKE_PANE_FILE" ;;
    display-message) echo "${FAKE_ALT:-0}" ;;
    *) exit 1 ;;
esac
EOF

cat > "$BIN_DIR/curl" << 'EOF'
#!/bin/bash
for arg in "$@"; do
    case "$arg" in
        caption=*) printf '%s\n' "${arg#caption=}" > "$CURL_CAPTION_FILE" ;;
        document=@*) cp "${arg#document=@}" "$CURL_DOC_FILE" ;;
    esac
done
echo '{"ok":true}'
EOF

chmod +x "$BIN_DIR/tmux" "$BIN_DIR/curl"

export FAKE_PANE_FILE="$TEST_DIR/pane.txt"
export CURL_CAPTION_FILE="$TEST_DIR/caption.txt"
export CURL_DOC_FILE="$TEST_DIR/doc.html"

# Write a fixture pane of N numbered lines, optionally followed by blank rows
make_pane() {
    local count="$1"
    local blanks="${2:-0}"
    : > "$FAKE_PANE_FILE"
    for i in $(seq 1 "$count"); do
        printf 'line-%03d\n' "$i" >> "$FAKE_PANE_FILE"
    done
    for _ in $(seq 1 "$blanks"); do
        echo "" >> "$FAKE_PANE_FILE"
    done
}

run_preview() {
    rm -f "$CURL_CAPTION_FILE" "$CURL_DOC_FILE"
    PATH="$BIN_DIR:$PATH" CLAUDE_HOME="$MOCK_CLAUDE_HOME" CLAUDE_SESSION=test \
        "$PREVIEW_SCRIPT" "$@" 2>&1
}

caption() {
    cat "$CURL_CAPTION_FILE" 2>/dev/null || true
}

doc_has() {
    grep -q -- "$1" "$CURL_DOC_FILE" 2>/dev/null
}

# -----------------------------------------------------------------------------
# Test: requested count smaller than pane is honored
# -----------------------------------------------------------------------------
echo "Line count trimming:"

make_pane 41
FAKE_ALT=1 run_preview 10 > /dev/null

if [ "$(caption)" = "📺 [test] Last 10 lines" ]; then
    pass "Caption reports requested count when enough lines exist"
else
    fail "Unexpected caption for 10 lines" "got: $(caption)"
fi

if doc_has "line-041" && doc_has "line-032" && ! doc_has "line-031"; then
    pass "Only the last 10 lines are sent"
else
    fail "Document does not contain exactly the last 10 lines"
fi

# -----------------------------------------------------------------------------
# Test: trailing blank rows are not counted
# -----------------------------------------------------------------------------
make_pane 30 15
FAKE_ALT=0 run_preview 5 > /dev/null

if doc_has "line-030" && doc_has "line-026" && ! doc_has "line-025"; then
    pass "Trailing blank rows are stripped before trimming"
else
    fail "Trailing blank rows displaced real output"
fi

# -----------------------------------------------------------------------------
# Test: fewer lines available than requested
# -----------------------------------------------------------------------------
echo ""
echo "Short capture reporting:"

make_pane 41
FAKE_ALT=1 run_preview 200 > /dev/null

if [ "$(caption)" = "📺 [test] Last 41 lines (requested 200; fullscreen TUI has no scrollback)" ]; then
    pass "Caption explains fullscreen TUI limit"
else
    fail "Unexpected caption for alt-screen short capture" "got: $(caption)"
fi

if doc_has "last 41 of 200 lines requested"; then
    pass "HTML title reports actual vs requested count"
else
    fail "HTML title missing actual vs requested count"
fi

make_pane 12
FAKE_ALT=0 run_preview 50 > /dev/null

if [ "$(caption)" = "📺 [test] Last 12 lines (requested 50; no more output available)" ]; then
    pass "Caption explains short history outside fullscreen TUI"
else
    fail "Unexpected caption for short history" "got: $(caption)"
fi

# -----------------------------------------------------------------------------
# Test: default (no args) uses 50 lines
# -----------------------------------------------------------------------------
make_pane 120
FAKE_ALT=0 run_preview > /dev/null

if [ "$(caption)" = "📺 [test] Last 50 lines" ] && doc_has "line-071" && ! doc_has "line-070"; then
    pass "Default sends last 50 lines"
else
    fail "Default line count not applied" "got: $(caption)"
fi

# -----------------------------------------------------------------------------
# Test: invalid line counts rejected
# -----------------------------------------------------------------------------
echo ""
echo "Argument validation:"

make_pane 41
for bad in "5x" "0"; do
    output=$(run_preview "$bad" || true)
    if echo "$output" | grep -q "Error: line count must be a positive integer" && [ ! -f "$CURL_CAPTION_FILE" ]; then
        pass "Rejects line count '$bad'"
    else
        fail "Accepted invalid line count '$bad'" "output: $output"
    fi
done

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════"
echo "  Results: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════"

[ "$FAIL" -eq 0 ]
