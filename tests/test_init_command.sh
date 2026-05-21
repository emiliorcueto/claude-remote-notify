#!/bin/bash
# =============================================================================
# test_init_command.sh - Integration tests for `claude-remote init`
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

assert_equals() {
    local expected="$1"
    local actual="$2"
    local message="${3:-}"
    TESTS_RUN=$((TESTS_RUN + 1))
    if [ "$expected" = "$actual" ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $message"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $message  (expected=$expected actual=$actual)"
    fi
}

# Stub HOME so we can write configs without polluting real ~/.claude
TMPHOME=$(mktemp -d -t init-test-XXXXXX)
export HOME="$TMPHOME"
export CLAUDE_HOME="$TMPHOME/.claude"
mkdir -p "$CLAUDE_HOME"

cleanup() {
    rm -rf "$TMPHOME" "$MOCKDIR" "$TMUXSTUB"
}
trap cleanup EXIT

# Global config required by init flow
cat > "$CLAUDE_HOME/telegram-remote.conf" <<EOF
TELEGRAM_BOT_TOKEN="FAKETOKEN"
TELEGRAM_CHAT_ID="-100123"
EOF
chmod 600 "$CLAUDE_HOME/telegram-remote.conf"

# Mock curl: respond based on endpoint in args
MOCKDIR=$(mktemp -d -t curlmock-XXXXXX)
cat > "$MOCKDIR/curl" <<'EOF'
#!/bin/bash
for arg in "$@"; do
    case "$arg" in
        *getMe*) printf '%s' '{"ok":true,"result":{"id":111,"is_bot":true,"username":"testbot"}}'; exit 0 ;;
        *getChat?chat_id*) printf '%s' '{"ok":true,"result":{"id":-100123,"type":"supergroup","is_forum":true}}'; exit 0 ;;
        *getChatMember*) printf '%s' '{"ok":true,"result":{"status":"administrator","can_manage_topics":true,"user":{"id":111}}}'; exit 0 ;;
        *createForumTopic*) printf '%s' '{"ok":true,"result":{"message_thread_id":777,"name":"demo","icon_color":7322096}}'; exit 0 ;;
        *sendMessage*) printf '%s' '{"ok":true,"result":{"message_id":1}}'; exit 0 ;;
    esac
done
printf '%s' '{"ok":false}'
EOF
chmod +x "$MOCKDIR/curl"
export PATH="$MOCKDIR:$PATH"

# Stub tmux so chain-to-start doesn't attach to a real terminal
TMUXSTUB=$(mktemp -d -t tmuxstub-XXXXXX)
cat > "$TMUXSTUB/tmux" <<'EOF'
#!/bin/bash
case "$1" in
    has-session) exit 1 ;;
    *) exit 0 ;;
esac
EOF
chmod +x "$TMUXSTUB/tmux"
export PATH="$TMUXSTUB:$PATH"

echo "Testing: claude-remote init --name demo --topic-name demo --no-start"

cd "$TMPHOME"
"$PROJECT_DIR/claude-remote" init --name demo --topic-name demo --no-start >/tmp/init.out 2>&1
rc=$?
assert_equals "0" "$rc" "init exits 0 on happy path"

if [ -f "$CLAUDE_HOME/sessions/demo.conf" ]; then
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: session config written"
else
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: session config missing"
fi

topic_id=$(grep '^TELEGRAM_TOPIC_ID=' "$CLAUDE_HOME/sessions/demo.conf" 2>/dev/null | cut -d'=' -f2 | tr -d '"')
assert_equals "777" "$topic_id" "TELEGRAM_TOPIC_ID is 777 from mock"

topic_name=$(grep '^TELEGRAM_TOPIC_NAME=' "$CLAUDE_HOME/sessions/demo.conf" 2>/dev/null | cut -d'=' -f2 | tr -d '"')
assert_equals "demo" "$topic_name" "TELEGRAM_TOPIC_NAME persisted"

reg_id=$(grep '^demo=' "$CLAUDE_HOME/topics-cache.conf" 2>/dev/null | cut -d'=' -f2)
assert_equals "777" "$reg_id" "registry updated with new topic"

# --- Second run with same name: should reuse via --reuse-existing flag ---
echo ""
echo "Testing: claude-remote init reuse path"
rm -f "$CLAUDE_HOME/sessions/demo.conf"
"$PROJECT_DIR/claude-remote" init --name demo --topic-name demo --no-start --reuse-existing --force >/tmp/init2.out 2>&1
rc=$?
assert_equals "0" "$rc" "reuse run exits 0"
topic_id=$(grep '^TELEGRAM_TOPIC_ID=' "$CLAUDE_HOME/sessions/demo.conf" 2>/dev/null | cut -d'=' -f2 | tr -d '"')
assert_equals "777" "$topic_id" "reused topic ID from registry"

# --- Test --no-test-message: sendMessage should not be called ---
echo ""
echo "Testing: --no-test-message"

# Add a sendMessage canary to the mock — if it gets called, the canary file is created
rm -f "$CLAUDE_HOME/sessions/demo-no-msg.conf"
SENDMSG_CANARY="$TMPHOME/sendmsg-called"
rm -f "$SENDMSG_CANARY"
cat > "$MOCKDIR/curl" <<EOF
#!/bin/bash
for arg in "\$@"; do
    case "\$arg" in
        *getMe*) printf '%s' '{"ok":true,"result":{"id":111,"is_bot":true,"username":"testbot"}}'; exit 0 ;;
        *getChat?chat_id*) printf '%s' '{"ok":true,"result":{"id":-100123,"type":"supergroup","is_forum":true}}'; exit 0 ;;
        *getChatMember*) printf '%s' '{"ok":true,"result":{"status":"administrator","can_manage_topics":true,"user":{"id":111}}}'; exit 0 ;;
        *createForumTopic*) printf '%s' '{"ok":true,"result":{"message_thread_id":888,"name":"x","icon_color":7322096}}'; exit 0 ;;
        *sendMessage*) touch "$SENDMSG_CANARY"; printf '%s' '{"ok":true,"result":{"message_id":1}}'; exit 0 ;;
    esac
done
printf '%s' '{"ok":false}'
EOF
chmod +x "$MOCKDIR/curl"

"$PROJECT_DIR/claude-remote" init --name demo-no-msg --topic-name demo-no-msg --no-start --no-test-message >/tmp/init3.out 2>&1
rc=$?
assert_equals "0" "$rc" "no-test-message run exits 0"
if [ ! -f "$SENDMSG_CANARY" ]; then
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: sendMessage was NOT called with --no-test-message"
else
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: sendMessage was called despite --no-test-message"
fi

# --- Test --non-interactive with pre-existing topic name (should fail) ---
echo ""
echo "Testing: --non-interactive with topic name conflict"

# Restore the standard mock for createForumTopic returning 777
cat > "$MOCKDIR/curl" <<'EOF'
#!/bin/bash
for arg in "$@"; do
    case "$arg" in
        *getMe*) printf '%s' '{"ok":true,"result":{"id":111,"is_bot":true,"username":"testbot"}}'; exit 0 ;;
        *getChat?chat_id*) printf '%s' '{"ok":true,"result":{"id":-100123,"type":"supergroup","is_forum":true}}'; exit 0 ;;
        *getChatMember*) printf '%s' '{"ok":true,"result":{"status":"administrator","can_manage_topics":true,"user":{"id":111}}}'; exit 0 ;;
        *createForumTopic*) printf '%s' '{"ok":true,"result":{"message_thread_id":777,"name":"demo","icon_color":7322096}}'; exit 0 ;;
        *sendMessage*) printf '%s' '{"ok":true,"result":{"message_id":1}}'; exit 0 ;;
    esac
done
printf '%s' '{"ok":false}'
EOF
chmod +x "$MOCKDIR/curl"

set +e
"$PROJECT_DIR/claude-remote" init --name conflict-test --topic-name demo --no-start --non-interactive >/tmp/init4.out 2>&1
rc=$?
set -e
if [ "$rc" -ne 0 ]; then
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: --non-interactive with topic conflict exits non-zero"
else
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: --non-interactive with topic conflict should fail"
fi

# --- Test telegram_chat_is_forum=false should fail with actionable error ---
echo ""
echo "Testing: non-forum group fails fast"

cat > "$MOCKDIR/curl" <<'EOF'
#!/bin/bash
for arg in "$@"; do
    case "$arg" in
        *getMe*) printf '%s' '{"ok":true,"result":{"id":111,"is_bot":true,"username":"testbot"}}'; exit 0 ;;
        *getChat?chat_id*) printf '%s' '{"ok":true,"result":{"id":-100123,"type":"supergroup","is_forum":false}}'; exit 0 ;;
    esac
done
printf '%s' '{"ok":false}'
EOF
chmod +x "$MOCKDIR/curl"

set +e
"$PROJECT_DIR/claude-remote" init --name nonforum --topic-name nonforum --no-start --non-interactive >/tmp/init5.out 2>&1
rc=$?
set -e
if [ "$rc" -ne 0 ]; then
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: non-forum group exits non-zero"
else
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: non-forum group should fail"
fi

echo ""
echo "=========================================="
echo "Tests run:    $TESTS_RUN"
echo "Tests passed: $TESTS_PASSED"
echo "Tests failed: $TESTS_FAILED"
echo "=========================================="
[ "$TESTS_FAILED" -eq 0 ]
