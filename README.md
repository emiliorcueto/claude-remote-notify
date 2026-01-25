# Claude Remote - Multi-Session Telegram Integration

Control multiple Claude CLI sessions remotely via Telegram, with each session isolated in its own **Topic thread**.

```
📱 Telegram Group (Forum Mode)
┌─────────────────────────────────────────────────────────┐
│  💬 project-alpha                                       │ ← Topic 1
│      Bot: 🔔 [project-alpha] Awaiting input             │
│      You: yes, continue                                 │
│      Bot: ✅ [project-alpha] Sent                       │
├─────────────────────────────────────────────────────────┤
│  💬 project-beta                                        │ ← Topic 2
│      Bot: ✅ [project-beta] Task complete               │
│      Bot: [📄 terminal-output.html]                     │
├─────────────────────────────────────────────────────────┤
│  💬 home-automation                                     │ ← Topic 3
│      Bot: 🔔 [home-automation] Permission needed        │
│      You: allow                                         │
└─────────────────────────────────────────────────────────┘
```

## Features

- **Multiple Sessions**: Run several Claude sessions simultaneously
- **Topic Isolation**: Each session has its own Telegram topic thread
- **Full Color Preview**: Terminal output sent as styled HTML (colors preserved!)
- **Bidirectional**: Receive notifications, send responses
- **Single Bot**: One Telegram bot manages all sessions
- **Zero Cost**: Uses free Telegram Bot API

## Quick Start

### 1. Create Telegram Bot & Group

```bash
# 1. Create bot with @BotFather → get token
# 2. Create a Telegram Group
# 3. Add your bot to the group (make it admin)
# 4. Enable Topics: Group Settings → Topics → Enable
# 5. Create topics for each session (e.g., "project-alpha", "project-beta")
```

### 2. Get Group & Topic IDs

```bash
# Send a message in each topic, then run:
./get-topic-ids.sh

# Output shows:
#   Chat ID: -1001234567890
#   → Topic ID: 123  (for "project-alpha" topic)
#   → Topic ID: 456  (for "project-beta" topic)
```

### 3. Install

```bash
./setup-telegram-remote.sh
```

### 4. Create Session Configs

```bash
# Interactive setup:
claude-remote --new

# Or manually create ~/.claude/sessions/myproject.conf:
TELEGRAM_BOT_TOKEN="123456:ABC..."
TELEGRAM_CHAT_ID="-1001234567890"
TELEGRAM_TOPIC_ID="123"
TMUX_SESSION="claude-myproject"
```

### 5. Start Sessions

```bash
# Start a session
claude-remote project-alpha

# In another terminal
claude-remote project-beta

# List all sessions
claude-remote --list
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Telegram Group (Forum Mode)                     │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐               │
│  │Topic: alpha │   │Topic: beta  │   │Topic: gamma │               │
│  │(ID: 123)    │   │(ID: 456)    │   │(ID: 789)    │               │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘               │
└─────────┼─────────────────┼─────────────────┼───────────────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
    ┌───────────┐     ┌───────────┐     ┌───────────┐
    │ Listener  │     │ Listener  │     │ Listener  │
    │ (alpha)   │     │ (beta)    │     │ (gamma)   │
    │ filters   │     │ filters   │     │ filters   │
    │ topic=123 │     │ topic=456 │     │ topic=789 │
    └─────┬─────┘     └─────┬─────┘     └─────┬─────┘
          │                 │                 │
          ▼                 ▼                 ▼
    ┌───────────┐     ┌───────────┐     ┌───────────┐
    │   tmux    │     │   tmux    │     │   tmux    │
    │claude-    │     │claude-    │     │claude-    │
    │  alpha    │     │   beta    │     │  gamma    │
    └───────────┘     └───────────┘     └───────────┘
```

**Key Points:**
- Single Telegram Bot serves all sessions
- Each listener filters messages by `message_thread_id` (Topic ID)
- Messages sent TO a topic go to that session's tmux
- Notifications FROM a session go to its topic

## Commands

### Terminal Commands

```bash
# Session Management
claude-remote                    # Start/attach "default" session
claude-remote myproject          # Start/attach "myproject" session
claude-remote myproject --kill   # Stop session and listener
claude-remote --list             # List all sessions
claude-remote --status           # Show all session statuses
claude-remote --new              # Interactive: create new session

# Notification Toggle (global)
claude-notify on                 # Enable notifications
claude-notify off                # Disable notifications
```

### Telegram Commands (in topic)

| Command | Description |
|---------|-------------|
| `/help` | Show all available commands |
| `/status` | Show session status + recent output |
| `/ping` | Test listener connectivity |
| **Preview** | |
| `/preview` | Send last 50 lines (with colors) |
| `/preview 100` | Send last 100 lines |
| `/preview back 1` | Send previous exchange |
| `/preview help` | Show preview help |
| `/output` | Alias for `/preview` (same options) |
| **Notifications** | |
| `/notify` | Show notify help (same as `/notify help`) |
| `/notify on` | Enable notifications |
| `/notify off` | Disable notifications |
| `/notify status` | Check notification state |
| `/notify config` | Show full configuration |
| `/notify start` | Start listener (if not running) |
| `/notify kill` | Stop listener |
| `/notify help` | Show notify help |
| **Other** | |
| `(any text)` | Send directly to Claude |

### Slash Commands (in Claude)

| Command | Description |
|---------|-------------|
| `/remote-preview-output` | Send terminal output with colors |
| `/remote-preview-output 100` | Last 100 lines |
| `/remote-preview-output back 1` | Previous exchange |
| `/remote-preview-output help` | Show all arguments |
| `/remote-notify on` | Enable notifications |
| `/remote-notify off` | Disable notifications |
| `/remote-notify status` | Check notification/listener state |
| `/remote-notify config` | Show full configuration |
| `/remote-notify start` | Start Telegram listener |
| `/remote-notify kill` | Stop Telegram listener |
| `/remote-notify help` | Show all commands |

## File Structure

```
~/.claude/
├── telegram-remote.conf          # Global/default config (optional)
├── notifications-enabled         # Flag file (presence = enabled)
├── settings.json                 # Claude Code hooks config
├── settings.json.backup          # Backup (created during install if settings existed)
├── cleanup-<session>.sh          # Auto-generated cleanup script per session
├── sessions/                     # Per-session configs
│   ├── project-alpha.conf
│   ├── project-beta.conf
│   └── myproject.conf
├── pids/                         # Listener PID files
│   ├── listener-project-alpha.pid
│   └── listener-project-beta.pid
├── logs/                         # Listener logs
│   ├── listener-project-alpha.log
│   └── listener-project-beta.log
├── hooks/
│   ├── telegram-notify.sh        # Send notifications (called by Claude hooks)
│   ├── telegram-listener.py      # Receive messages (runs in background)
│   ├── telegram-preview.sh       # Send terminal output as HTML
│   └── remote-notify.sh          # Unified notification control
└── commands/                     # Slash commands for Claude CLI
    ├── remote-notify.md          # /remote-notify <cmd>
    └── remote-preview-output.md  # /remote-preview-output [args]

~/.local/bin/
├── claude-remote                 # Main launcher
├── claude-notify                 # Notification toggle (CLI)
└── get-topic-ids.sh              # Topic ID discovery helper
```

## Session Config Format

### Session Config vs Global Config

| Config Type | Location | Purpose |
|-------------|----------|---------|
| **Global** | `~/.claude/telegram-remote.conf` | Default/fallback for single-session use |
| **Session** | `~/.claude/sessions/<name>.conf` | Per-session settings with Topic ID |

**How it works:**
1. When you run `claude-remote myproject`, it looks for `~/.claude/sessions/myproject.conf`
2. If not found, it falls back to `~/.claude/telegram-remote.conf`
3. If neither exists, it shows an error

**When to use which:**
- **Single session, no group:** Use global config only
- **Multiple sessions with Topics:** Create session configs for each

**Creating configs:**
```bash
# Global config (created during setup)
./setup-telegram-remote.sh

# Session config (interactive)
claude-remote --new

# Session config (manual)
vim ~/.claude/sessions/myproject.conf
```

### Config File Format

```bash
# ~/.claude/sessions/myproject.conf

TELEGRAM_BOT_TOKEN="123456789:ABCdef..."
TELEGRAM_CHAT_ID="-1001234567890"      # Group ID (negative, starts with -100)
TELEGRAM_TOPIC_ID="123"                 # Topic thread ID
TMUX_SESSION="claude-myproject"         # Optional: custom tmux name
```

## Getting Topic IDs

### Method 1: Use Helper Script

```bash
# After sending messages in your topics:
./get-topic-ids.sh
```

### Method 2: Manual (getUpdates API)

```bash
# Send a message in your topic, then:
curl "https://api.telegram.org/bot<TOKEN>/getUpdates" | jq '.result[-1].message'

# Look for "message_thread_id" - that's your Topic ID
```

### Method 3: Forward from Topic

Forward any message from the topic to @RawDataBot - it will show the `message_thread_id`.

## Terminal Output Preview

The `/remote-preview-output` command sends terminal output as a styled HTML file:

```
You (in Claude): /remote-preview-output 100

📱 Telegram receives:
[📄 claude-terminal-myproject-20260124.html]
📺 [myproject] Last 100 lines

→ Tap to open in Telegram's built-in viewer
→ Full colors preserved (green diffs, red errors, etc.)
→ Pinch to zoom, scroll through
```

## Single-Session Mode

If you only need one session, you can skip Topics:

```bash
# Use global config (no topic ID)
~/.claude/telegram-remote.conf:
TELEGRAM_BOT_TOKEN="..."
TELEGRAM_CHAT_ID="123456789"    # Your personal chat ID (positive)
# No TELEGRAM_TOPIC_ID needed

# Start with default session
claude-remote
```

## Troubleshooting

### Messages not reaching Claude

1. Check listener is running: `claude-remote --list`
2. Check Topic ID matches: compare config with `get-topic-ids.sh` output
3. Check logs: `tail -f ~/.claude/logs/listener-myproject.log`

### Bot not receiving messages in group

1. Make bot an admin in the group
2. Disable "Group Privacy" in @BotFather: `/mybots` → Bot Settings → Group Privacy → Disable

### Topic ID not appearing

1. Ensure Topics are enabled: Group Settings → Topics
2. Send a new message in the topic
3. Run `get-topic-ids.sh` again

### HTML preview not showing colors

1. Ensure `ansi2html` is installed: `pip install ansi2html --break-system-packages`
2. Tap the HTML file to open (don't just preview)

### Listener starts but immediately stops

1. Check config file exists and has correct permissions (600)
2. Check bot token is valid: `curl https://api.telegram.org/bot<TOKEN>/getMe`
3. Review log: `tail -50 ~/.claude/logs/listener-<session>.log`

## Edge Cases & Known Behaviors

| Scenario | Behavior |
|----------|----------|
| No session config exists | Falls back to global `~/.claude/telegram-remote.conf` |
| No Topic ID + multiple sessions | Warning displayed, user must confirm to continue |
| Same Topic ID on two sessions | **Blocked** - second session refuses to start |
| Listener crashes | Auto-retries up to 3 times with exponential backoff; notifies via Telegram |
| Listener gives up after 3 retries | Sends final "crashed" notification; must restart manually |
| Ctrl-C in Claude | Claude exits → shell shows options → typing `exit` kills listener too |
| `exit` from tmux shell | Listener automatically stopped, tmux session closes |
| Detach with Ctrl-b, d | Everything keeps running (Claude, listener, tmux) |
| Session name with special chars | Sanitized to alphanumeric, underscore, hyphen only |
| `/preview` without arguments | Sends last 50 lines (default) |
| `/preview back` without number | Defaults to `back 0` (current response) |
| `/notify` without subcommand | Shows help (same as `/notify help`) |
| `/notify start` when already running | Shows "already running" message, no action |
| `/notify kill` from Telegram | Works - kills the listener that received the command |
| Existing `settings.json` | Hooks are merged, not overwritten; backup created |
| Notifications disabled | Listener still runs (can receive messages, just no outbound alerts) |
| Chat ID empty during setup | Setup continues but test message will fail |
| Invalid bot token | Listener starts but fails to connect; check logs |

## Bot Privacy Mode (Important!)

Telegram bots have "Group Privacy" enabled by default. This means bots in groups can **only** see:
- Messages starting with `/`
- Messages that @mention the bot
- Replies to bot messages

**If you don't disable Group Privacy, your responses like "yes, continue" won't reach Claude!**

To disable:
1. Message @BotFather
2. `/mybots` → Select your bot
3. Bot Settings → Group Privacy → **Disable**

> **Note:** This is about what messages the bot can "hear" - not about your data privacy. Your messages still go through Telegram's servers (unavoidable), but the listener runs entirely on your local machine.

## Requirements

- **Python 3** with:
  - `requests` (`pip install requests --break-system-packages`)
  - `ansi2html` (`pip install ansi2html --break-system-packages`)
- **tmux** for session management
- **curl** for API calls
- **Claude Code** CLI

## Security

- Bot token stored with 600 permissions
- Each listener only processes messages from its configured topic
- Messages from unauthorized chats/topics are ignored
- All communication stays local (no cloud servers)

## License

MIT - Use freely!
