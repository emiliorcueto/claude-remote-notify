#!/bin/bash
# =============================================================================
# get-topic-ids.sh - Discover Topic IDs from a Telegram Forum Group
# =============================================================================
#
# This helper script retrieves recent messages from your bot and shows
# the topic (message_thread_id) for each message.
#
# Usage:
#   1. Disable Group Privacy: @BotFather → /mybots → Bot Settings → Group Privacy → Disable
#   2. Enable Topics in your Telegram Group (Group Settings → Topics)
#   3. Create topics for each Claude session (e.g., "project-a", "project-b")
#   4. Send a message in each topic
#   5. Run this script IMMEDIATELY to see the Topic IDs
#
# Options:
#   --poll, -p     Live polling mode - watches for messages in real-time
#   --debug, -d    Show raw API response for troubleshooting
#
# Note: Telegram marks updates as "consumed" after each API call.
#       If you see "No pending updates", send new messages and re-run immediately.
#
# =============================================================================

set -e

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
CONFIG_FILE="$CLAUDE_HOME/telegram-remote.conf"

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check for flags
DEBUG=false
POLL=false
for arg in "$@"; do
    case $arg in
        --debug|-d) DEBUG=true ;;
        --poll|-p) POLL=true ;;
    esac
done

# Load config or prompt for token
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "Enter your Telegram Bot Token:"
    read -p "> " TELEGRAM_BOT_TOKEN
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}              Telegram Topic ID Discovery                   ${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Verify bot token
echo "Verifying bot..."
bot_info=$(curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe")
if ! echo "$bot_info" | grep -q '"ok":true'; then
    echo -e "${RED}Error: Invalid bot token${NC}"
    echo "$bot_info"
    exit 1
fi
bot_username=$(echo "$bot_info" | grep -o '"username":"[^"]*"' | cut -d'"' -f4)
echo -e "${GREEN}✓ Bot: @$bot_username${NC}"
echo ""

# Check for webhook (blocks getUpdates)
webhook_info=$(curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo")
webhook_url=$(echo "$webhook_info" | grep -o '"url":"[^"]*"' | cut -d'"' -f4)

if [ -n "$webhook_url" ]; then
    echo -e "${RED}⚠ Webhook is set: $webhook_url${NC}"
    echo -e "${YELLOW}Webhooks block getUpdates. Removing webhook...${NC}"
    curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/deleteWebhook" > /dev/null
    echo -e "${GREEN}Webhook removed.${NC}"
    echo ""
    echo "Please send a new message in your topic, then run this script again."
    exit 0
fi

# Show pending update count
pending_count=$(echo "$webhook_info" | grep -o '"pending_update_count":[0-9]*' | cut -d':' -f2)
if [ -n "$pending_count" ] && [ "$pending_count" != "0" ]; then
    echo -e "${GREEN}✓ Pending updates: $pending_count${NC}"
else
    echo -e "${YELLOW}✓ No pending updates in queue${NC}"
fi
echo ""

# Poll mode - watch for messages in real-time
if $POLL; then
    echo -e "${CYAN}Live polling mode - send messages now (Ctrl+C to stop)${NC}"
    echo -e "${YELLOW}Tip: If only /commands work, Group Privacy is still ON${NC}"
    echo ""

    offset=0
    seen_ids=""
    while true; do
        response=$(curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates?limit=5&timeout=10&offset=$offset")

        # Check if we got any results
        if echo "$response" | grep -q '"update_id"'; then
            export TELEGRAM_RESPONSE="$response"
            result=$(python3 << 'POLL_PYTHON'
import json
import os

data = json.loads(os.environ['TELEGRAM_RESPONSE'])
max_id = 0
for update in data.get('result', []):
    update_id = update.get('update_id', 0)
    if update_id > max_id:
        max_id = update_id
    msg = update.get('message', {})
    if not msg:
        continue
    chat = msg.get('chat', {})
    print(f"MSG:{chat.get('title', 'Private')}|{chat.get('id')}|{chat.get('type')}|{msg.get('message_thread_id', '')}|{msg.get('text', '')[:50]}")
print(f"OFFSET:{max_id + 1}")
POLL_PYTHON
)
            # Parse and display results
            while IFS= read -r line; do
                if [[ "$line" == MSG:* ]]; then
                    IFS='|' read -r title chat_id chat_type topic_id text <<< "${line#MSG:}"
                    echo -e "${GREEN}✓ Message received!${NC}"
                    echo "  Chat: $title"
                    echo "  Chat ID: $chat_id"
                    echo "  Type: $chat_type"
                    if [ -n "$topic_id" ]; then
                        echo -e "  ${GREEN}→ Topic ID: $topic_id${NC}"
                    else
                        echo "  → Topic ID: (none)"
                    fi
                    echo "  Text: $text"
                    echo ""
                elif [[ "$line" == OFFSET:* ]]; then
                    offset="${line#OFFSET:}"
                fi
            done <<< "$result"
        else
            printf "." >&2
        fi
        sleep 1
    done
    exit 0
fi

echo "Fetching recent messages from bot..."
echo ""

# Get updates
response=$(curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates?limit=20")

if $DEBUG; then
    echo -e "${YELLOW}=== DEBUG: Raw API Response ===${NC}"
    echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
    echo -e "${YELLOW}=== END DEBUG ===${NC}"
    echo ""
fi

if ! echo "$response" | grep -q '"ok":true'; then
    echo "Error: Could not fetch updates"
    echo "$response"
    exit 1
fi

# Parse and display messages with topic info
export TELEGRAM_RESPONSE="$response"
python3 << 'PYTHON_SCRIPT'
import json
import os
import sys

data = json.loads(os.environ['TELEGRAM_RESPONSE'])

result = data.get('result', [])

if not data.get('ok'):
    print("API returned error")
    sys.exit(1)

if not result or len(result) == 0:
    print("No pending updates found.")
    print("")
    print("Try: ./get-topic-ids.sh --poll")
    print("     (watches for messages in real-time)")
    sys.exit(0)

print("Recent Messages with Topic IDs:")
print("─" * 60)
print()

seen_topics = {}

for update in data['result']:
    msg = update.get('message', {})
    
    chat = msg.get('chat', {})
    chat_id = chat.get('id')
    chat_title = chat.get('title', 'Private Chat')
    chat_type = chat.get('type', 'unknown')
    
    thread_id = msg.get('message_thread_id', '')
    text = msg.get('text', '')[:50]
    
    from_user = msg.get('from', {}).get('username', 'unknown')
    
    # Track unique topics
    key = f"{chat_id}:{thread_id}"
    if key in seen_topics:
        continue
    seen_topics[key] = True
    
    print(f"  Chat: {chat_title}")
    print(f"  Chat ID: {chat_id}")
    print(f"  Type: {chat_type}")
    
    if thread_id:
        print(f"  \033[32m→ Topic ID: {thread_id}\033[0m")
    else:
        print(f"  → Topic ID: (none - general chat)")
    
    if text:
        print(f"  Message: {text}...")
    
    print()

print("─" * 60)
print()
print("To use a topic, add to your session config:")
print('  TELEGRAM_TOPIC_ID="<topic_id>"')
print()
PYTHON_SCRIPT

echo ""
echo "Tips:"
echo "  • If no messages found: send new message, run script IMMEDIATELY after"
echo "  • Telegram marks updates as 'consumed' after each getUpdates call"
echo "  • Stop any running listeners first (they consume updates)"
echo "  • Bot must be admin AND have Group Privacy disabled (@BotFather)"
echo "  • Run with --debug to see raw API response"
echo ""
