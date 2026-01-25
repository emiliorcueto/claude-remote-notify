#!/bin/bash
# =============================================================================
# get-topic-ids.sh - Discover Topic IDs from a Telegram Forum Group
# =============================================================================
#
# This helper script retrieves recent messages from your bot and shows
# the topic (message_thread_id) for each message.
#
# Usage:
#   1. Enable Topics in your Telegram Group (Group Settings → Topics)
#   2. Create topics for each Claude session (e.g., "project-a", "project-b")
#   3. Send a message in each topic
#   4. Run this script to see the Topic IDs
#
# =============================================================================

set -e

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
CONFIG_FILE="$CLAUDE_HOME/telegram-remote.conf"

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

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

echo "Fetching recent messages from bot..."
echo ""

# Get updates
response=$(curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates?limit=20")

if ! echo "$response" | grep -q '"ok":true'; then
    echo "Error: Could not fetch updates"
    echo "$response"
    exit 1
fi

# Parse and display messages with topic info
echo "$response" | python3 << 'PYTHON_SCRIPT'
import json
import sys

data = json.load(sys.stdin)

if not data.get('ok') or not data.get('result'):
    print("No messages found. Make sure to:")
    print("  1. Send messages in your topic threads")
    print("  2. The bot is added to the group")
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
echo "  • If you don't see Topic IDs, make sure Topics are enabled in the group"
echo "  • Send a new message in each topic, then run this script again"
echo "  • The bot must be an admin in the group to receive all messages"
echo ""
