#!/bin/bash
# =============================================================================
# smoke_init_live.sh - Opt-in live smoke test against a real Telegram group
# =============================================================================
#
# Runs `claude-remote init` against real Telegram, asserts side effects, then
# cleans up the created topic, session config, and registry entry.
#
# Credentials: by default, sources ~/.claude/telegram-remote.conf and uses
# TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from there. Override with env vars
# SMOKE_BOT_TOKEN / SMOKE_CHAT_ID if you want to target a different bot/group
# (e.g., a dedicated CI test bot).
#
# Bot requirements:
#   - Admin of the chat with can_manage_topics (required)
#   - can_delete_messages (recommended; without it auto-cleanup will WARN)
#
# Optional env vars:
#   SMOKE_KEEP        - If set to "1", skip cleanup (leave topic + config in place)
#
# Usage:
#   bash tests/smoke_init_live.sh                                      # uses global config
#   SMOKE_BOT_TOKEN=... SMOKE_CHAT_ID=... bash tests/smoke_init_live.sh # override
#
# Exit codes:
#   0 - all assertions passed AND cleanup succeeded
#   1 - assertion failure
#   2 - missing credentials / preconditions
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}PASS${NC}: $1"; }
fail() { echo -e "  ${RED}FAIL${NC}: $1"; FAILURES=$((FAILURES + 1)); }
warn() { echo -e "  ${YELLOW}WARN${NC}: $1"; }

FAILURES=0

# --- Resolve credentials ---
# Priority: SMOKE_* env vars > ~/.claude/telegram-remote.conf
GLOBAL_CONF="$HOME/.claude/telegram-remote.conf"
if [ -z "${SMOKE_BOT_TOKEN:-}" ] || [ -z "${SMOKE_CHAT_ID:-}" ]; then
    if [ -f "$GLOBAL_CONF" ]; then
        SMOKE_BOT_TOKEN="${SMOKE_BOT_TOKEN:-$(grep '^TELEGRAM_BOT_TOKEN=' "$GLOBAL_CONF" | cut -d'=' -f2- | tr -d '"' | tr -d "'")}"
        SMOKE_CHAT_ID="${SMOKE_CHAT_ID:-$(grep '^TELEGRAM_CHAT_ID=' "$GLOBAL_CONF" | cut -d'=' -f2- | tr -d '"' | tr -d "'")}"
    fi
fi

if [ -z "${SMOKE_BOT_TOKEN:-}" ] || [ -z "${SMOKE_CHAT_ID:-}" ]; then
    echo "No credentials found. Either:"
    echo "  - Configure $GLOBAL_CONF (see setup-telegram-remote.sh), or"
    echo "  - Set SMOKE_BOT_TOKEN and SMOKE_CHAT_ID env vars."
    exit 2
fi

SMOKE_NAME="init-smoke-$$"
SMOKE_TOPIC_NAME="Init Smoke $$"

# Isolate HOME so we don't pollute the user's real ~/.claude
TMPHOME=$(mktemp -d -t init-smoke-XXXXXX)
export HOME="$TMPHOME"
export CLAUDE_HOME="$TMPHOME/.claude"
mkdir -p "$CLAUDE_HOME"

cat > "$CLAUDE_HOME/telegram-remote.conf" <<EOF
TELEGRAM_BOT_TOKEN="$SMOKE_BOT_TOKEN"
TELEGRAM_CHAT_ID="$SMOKE_CHAT_ID"
EOF
chmod 600 "$CLAUDE_HOME/telegram-remote.conf"

# Captured state for cleanup
CREATED_TOPIC_ID=""

# --- Cleanup trap ---
cleanup() {
    local exit_code=$?
    echo ""
    if [ "${SMOKE_KEEP:-0}" = "1" ]; then
        warn "SMOKE_KEEP=1 set — leaving topic, config, and HOME ($TMPHOME) in place."
        exit $exit_code
    fi

    # shellcheck source=/dev/null
    source "$PROJECT_DIR/lib/common.sh"

    if [ -n "$CREATED_TOPIC_ID" ]; then
        echo "Cleanup: deleting topic $CREATED_TOPIC_ID..."
        if telegram_delete_topic "$SMOKE_BOT_TOKEN" "$SMOKE_CHAT_ID" "$CREATED_TOPIC_ID"; then
            pass "Topic deleted"
        else
            warn "Failed to delete topic $CREATED_TOPIC_ID — delete manually in Telegram. (Bot may lack can_delete_messages.)"
        fi
    fi

    rm -rf "$TMPHOME"
    pass "Removed temp HOME $TMPHOME"

    if [ "$FAILURES" -gt 0 ]; then
        echo -e "${RED}Smoke test FAILED with $FAILURES assertion failure(s).${NC}"
        exit 1
    fi
    echo -e "${GREEN}Smoke test PASSED.${NC}"
    exit 0
}
trap cleanup EXIT INT TERM

# --- Run init (no-start, since this is a CI/smoke context) ---
echo "Running: claude-remote init --name $SMOKE_NAME --topic-name '$SMOKE_TOPIC_NAME' --no-start --non-interactive"
"$PROJECT_DIR/claude-remote" init \
    --name "$SMOKE_NAME" \
    --topic-name "$SMOKE_TOPIC_NAME" \
    --no-start \
    --non-interactive
rc=$?
if [ $rc -ne 0 ]; then
    fail "init exited non-zero ($rc)"
    exit 1
fi
pass "init exited 0"

# --- Assertions ---
CONFIG="$CLAUDE_HOME/sessions/$SMOKE_NAME.conf"
if [ -f "$CONFIG" ]; then
    pass "Session config exists at $CONFIG"
else
    fail "Session config missing"
fi

CREATED_TOPIC_ID=$(grep '^TELEGRAM_TOPIC_ID=' "$CONFIG" | cut -d'=' -f2 | tr -d '"')
if [ -n "$CREATED_TOPIC_ID" ] && [ "$CREATED_TOPIC_ID" -gt 0 ] 2>/dev/null; then
    pass "TELEGRAM_TOPIC_ID is a positive integer ($CREATED_TOPIC_ID)"
else
    fail "TELEGRAM_TOPIC_ID is missing or invalid: '$CREATED_TOPIC_ID'"
fi

TOPIC_NAME_PERSISTED=$(grep '^TELEGRAM_TOPIC_NAME=' "$CONFIG" | cut -d'=' -f2 | tr -d '"')
if [ "$TOPIC_NAME_PERSISTED" = "$SMOKE_TOPIC_NAME" ]; then
    pass "TELEGRAM_TOPIC_NAME persisted correctly"
else
    fail "TELEGRAM_TOPIC_NAME mismatch: expected '$SMOKE_TOPIC_NAME', got '$TOPIC_NAME_PERSISTED'"
fi

REGISTRY="$CLAUDE_HOME/topics-cache.conf"
if [ -f "$REGISTRY" ]; then
    pass "Registry file exists"
    if grep -q "=$CREATED_TOPIC_ID$" "$REGISTRY"; then
        pass "Registry contains created topic ID"
    else
        fail "Registry missing entry for topic $CREATED_TOPIC_ID"
    fi
else
    fail "Registry file not created"
fi

# --- Reuse path: second init with same topic-name + --reuse-existing ---
echo ""
echo "Running reuse path: claude-remote init --name ${SMOKE_NAME}-2 --topic-name '$SMOKE_TOPIC_NAME' --reuse-existing --no-start --non-interactive"
"$PROJECT_DIR/claude-remote" init \
    --name "${SMOKE_NAME}-2" \
    --topic-name "$SMOKE_TOPIC_NAME" \
    --reuse-existing \
    --no-start \
    --non-interactive
rc=$?
if [ $rc -ne 0 ]; then
    fail "reuse init exited non-zero ($rc)"
else
    pass "reuse init exited 0"
    REUSED_ID=$(grep '^TELEGRAM_TOPIC_ID=' "$CLAUDE_HOME/sessions/${SMOKE_NAME}-2.conf" | cut -d'=' -f2 | tr -d '"')
    if [ "$REUSED_ID" = "$CREATED_TOPIC_ID" ]; then
        pass "Reuse path returned same topic ID ($REUSED_ID)"
    else
        fail "Reuse path produced different ID: expected $CREATED_TOPIC_ID, got $REUSED_ID"
    fi
fi

# Trap fires here for cleanup + final summary
