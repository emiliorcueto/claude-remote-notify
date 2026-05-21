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

### 1. Create Telegram Bot

```bash
# In Telegram, message @BotFather:
/newbot              # Create bot, save the token
/mybots              # Select your new bot
→ Bot Settings
→ Group Privacy
→ Turn off           # CRITICAL! See note below
```

> ⚠️ **Group Privacy MUST be disabled.** With privacy ON, bot only receives `/commands` in forum groups - regular messages like "yes, continue" are ignored.

### 2. Create Group & Add Bot

```bash
# 1. Create a Telegram Group
# 2. Enable Topics: Group Settings → Topics → Enable
# 3. Add bot to group
# 4. Make bot an admin
# 5. Create topics (e.g., "project-alpha", "project-beta")
```

> ⚠️ **If you changed Group Privacy after the bot was already in a group**, you must **remove the bot and re-add it** for the setting to take effect.

### 3. Get Group & Topic IDs

```bash
# Send a message in each topic, then run:
./get-topic-ids.sh

# If no messages found, use poll mode:
./get-topic-ids.sh --poll
# Then send messages while it's running

# Output shows:
#   Chat ID: -1001234567890
#   → Topic ID: 123  (for "project-alpha" topic)
#   → Topic ID: 456  (for "project-beta" topic)
```

### 4. Install & Configure Sessions

```bash
# First run: installs files, configures bot, creates session configs
./setup-telegram-remote.sh

# Setup prompts to create multiple session configs (one per topic)
# Answer 'y' to "Create a session config?" for each session you need
```

**Re-running setup:**
```bash
# If already installed, offers to add more sessions
./setup-telegram-remote.sh

# Force full reinstall
./setup-telegram-remote.sh --force

# Development mode: symlinks files instead of copying
# Changes to project files take effect immediately
./setup-telegram-remote.sh --dev
```

### 5. Manual Session Config (Alternative)

```bash
# Or manually create ~/.claude/sessions/myproject.conf:
TELEGRAM_BOT_TOKEN="123456:ABC..."
TELEGRAM_CHAT_ID="-1001234567890"
TELEGRAM_TOPIC_ID="123"
TMUX_SESSION="claude-myproject"
```

### 6. Start Sessions

```bash
# Start a session
claude-remote project-alpha

# In another terminal
claude-remote project-beta

# List all sessions
claude-remote --list
```

**Session startup hints:**
- Detach: `Ctrl+b, d` (keeps session running in background)
- Text select: `Option+drag` on Mac (mouse mode enabled for touchpad scrolling)

### One-shot session bootstrap with `init`

From any project directory:

```bash
claude-remote init
```

This will:
1. Use the directory name as the session name (override with `--name`)
2. Verify the bot is admin of your group with **Manage Topics** permission
3. Auto-create a new Telegram forum topic with a deterministic icon color
4. Write `~/.claude/sessions/<name>.conf`
5. Send a minimal welcome message to the new topic
6. Launch the session immediately

**Requirements:**
- Group must be a supergroup with Topics enabled (Group Settings → Topics → On)
- Bot must be promoted to admin with **Manage Topics** permission

**Flags:**

| Flag | Purpose |
|---|---|
| `--name <session>` | Override session name (default: `$(basename $PWD)`) |
| `--topic-name <text>` | Override topic display name (default: session name) |
| `--reuse-existing` | If a topic with this name is in the local registry, reuse it instead of prompting |
| `--non-interactive` | Fail instead of prompting on conflicts |
| `--force` | Overwrite an existing session config without asking |
| `--no-test-message` | Skip the welcome message |
| `--no-start` | Don't launch the session after init |

**Note on topic discovery:** Telegram's Bot API doesn't expose a "list topics" endpoint, so duplicate detection is based on a local registry at `~/.claude/topics-cache.conf` of topics this CLI has created. Topics created in Telegram directly are not tracked.

**Live smoke test:** `tests/smoke_init_live.sh` exercises the full flow against a real Telegram group and cleans up after itself. By default it reads credentials from `~/.claude/telegram-remote.conf` — no env-var setup required. To target a different bot/group, override with `SMOKE_BOT_TOKEN` / `SMOKE_CHAT_ID`. The bot needs `can_manage_topics` and (for auto-cleanup) `can_delete_messages` admin permissions.

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
# Start/attach sessions
claude-remote                    # Uses ~/.claude/sessions/default.conf
                                 # (falls back to telegram-remote.conf if no default.conf)
claude-remote myproject          # Uses ~/.claude/sessions/myproject.conf
                                 # (Topic ID comes from that config file)

# Session management
claude-remote myproject --kill   # Stop session and listener
claude-remote --list             # List sessions and exit (does NOT open Claude)
claude-remote --status           # Show session statuses and exit
claude-remote --new              # Create new session config (same as setup script)

# Notification Toggle (global)
claude-notify on                 # Enable notifications
claude-notify off                # Disable notifications
```

> **Note:** Session name ≠ Topic ID. Each session config (`~/.claude/sessions/<name>.conf`) specifies its own Topic ID. Running `claude-remote myproject` uses whatever Topic ID is configured in `myproject.conf`.

### Telegram Commands (in topic)

| Command | Description |
|---------|-------------|
| `/help` | Show all available commands |
| `/status` | Show session status + recent output |
| `/ping` | Test listener connectivity |
| **Context** | |
| `/clear` | Clear Claude context |
| `/compact` | Compact Claude context |
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
| **Media** | |
| 📷 Photo | Downloaded, sent as `[Image: /path]` |
| 📄 Document | Downloaded, sent as `[Document: /path]` |
| ❌ Voice/Video | Not supported (error message sent) |
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
├── lib/
│   └── common.sh                 # Shared security library (validation, sanitization)
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

## Media Support

Send photos and documents via Telegram to share them with Claude:

```
📱 Telegram:
[Send photo of error screenshot]

→ Listener downloads to /tmp/claude-telegram/
→ Injects: [Image: /tmp/claude-telegram/session-photo_20260127_143022.jpg]

Claude sees the image and can analyze it!
```

**Supported:**
- 📷 Photos (all sizes, up to 20MB)
- 📄 Documents (PDFs, code files, etc.)
- Captions included with media

**Not Supported:**
- ❌ Voice messages
- ❌ Videos
- ❌ Stickers/GIFs
- ❌ Audio files

**How it works:**
1. Send photo/document in your Telegram topic
2. Listener downloads file to `/tmp/claude-telegram/`
3. File path injected to Claude as `[Image: /path]` or `[Document: /path]`
4. Claude can read/analyze the file
5. Files cleaned up when session exits

> **Note:** Files are stored temporarily in `/tmp/claude-telegram/` and automatically cleaned up when the session ends.

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

1. **Disable Group Privacy** in @BotFather:
   - `/mybots` → Select bot → Bot Settings → Group Privacy → Turn off
2. **Remove and re-add bot** to the group (required after changing privacy setting!)
3. Make bot an admin in the group
4. Test with `./get-topic-ids.sh --poll` - send a regular message (not /command)

### Only /commands work, regular messages ignored

This means Group Privacy is still enabled OR the bot needs to be re-added:

1. Verify in @BotFather: `/mybots` → Bot Settings → Group Privacy → should say "disabled"
2. **Remove bot from group completely**
3. **Add bot back to group**
4. Make bot admin again
5. Test with `./get-topic-ids.sh --poll`

### Topic ID not appearing

1. Ensure Topics are enabled: Group Settings → Topics
2. Use poll mode: `./get-topic-ids.sh --poll`
3. Send a message while poll is running
4. If only `/commands` appear, see "Only /commands work" above

### HTML preview not showing colors

1. Ensure `ansi2html` is installed: `pip install ansi2html --user`
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
| `/clear` when tmux not running | Shows error message, no action |
| `/compact` when tmux not running | Shows error message, no action |
| `/preview` without arguments | Sends last 50 lines (default) |
| `/preview back` without number | Defaults to `back 0` (current response) |
| `/notify` without subcommand | Shows help (same as `/notify help`) |
| `/notify start` when already running | Shows "already running" message, no action |
| `/notify kill` from Telegram | Works - kills the listener that received the command |
| Existing `settings.json` | Hooks are merged, not overwritten; backup created |
| Notifications disabled | Listener still runs (can receive messages, just no outbound alerts) |
| Chat ID empty during setup | Setup continues but test message will fail |
| Invalid bot token | Listener starts but fails to connect; check logs |
| Touchpad scroll in tmux | Scrolls through scrollback buffer (mouse mode enabled) |
| Text selection in tmux | Use Option+drag on Mac (mouse mode intercepts normal drag) |

## Bot Privacy Mode (CRITICAL!)

Telegram bots have "Group Privacy" **enabled by default**. With privacy ON, bots can **only** see:
- Messages starting with `/` (commands)
- ~~Messages that @mention the bot~~ *(does NOT work in forum/topic groups!)*
- ~~Replies to bot messages~~ *(does NOT work in forum/topic groups!)*

**⚠️ In forum groups with Topics, ONLY `/commands` work until you disable Group Privacy!**

### How to Disable Group Privacy

```
1. Open Telegram, message @BotFather
2. Send: /mybots
3. Select your bot (e.g., @ERC_SessionBot)
4. Tap "Bot Settings"
5. Tap "Group Privacy"
6. Current status shown - tap "Turn off" if enabled
7. You should see: "Privacy mode is disabled for YourBot"
```

### Verifying It Worked

After disabling, the bot must be **removed and re-added** to the group for the change to take effect:

```
1. Remove bot from group (kick)
2. Add bot back to group
3. Make bot admin again
4. Send a regular message (not a /command)
5. Run: ./get-topic-ids.sh --poll
6. If you see the message, it's working!
```

### Troubleshooting

| Symptom | Cause |
|---------|-------|
| Only `/commands` received | Group Privacy still ON, or bot needs re-add |
| @mentions not received | Normal in forum groups - disable privacy instead |
| Setting shows "disabled" but doesn't work | Remove and re-add bot to group |

> **Note:** "Group Privacy" controls what messages the bot can "hear" - not your data privacy. Messages go through Telegram servers regardless, but the listener runs on your local machine.

## Development

### Setup Modes

| Mode | Command | Behavior |
|------|---------|----------|
| **Normal** | `./setup-telegram-remote.sh` | Copies files to `~/.claude/` |
| **Dev** | `./setup-telegram-remote.sh --dev` | Symlinks files to project |
| **Force** | `./setup-telegram-remote.sh --force` | Full reinstall |

**Development mode (`--dev`):**
- Creates symlinks from `~/.claude/hooks/` → project files
- Changes to project files take effect immediately
- No need to re-run setup after edits
- Useful for rapid iteration

**Normal mode (default):**
- Copies files to `~/.claude/`
- Must re-run setup to apply changes
- Works even if project is moved/deleted
- Recommended for end users

### Running Tests

```bash
# All tests
./tests/test_common.sh
./tests/test_setup.sh
./tests/test_claude_remote.sh
python3 -m pytest tests/test_security.py -v
```

## Requirements

- **Python 3** with:
  - `requests` (`pip install requests --user`)
  - `ansi2html` (`pip install ansi2html --user`)
- **tmux** for session management
- **curl** for API calls
- **Claude Code** CLI

## Security

### Data Protection
- Bot token stored with 600 permissions (owner read/write only)
- Config files validated for ownership and permissions before loading
- World-writable configs rejected (prevents privilege escalation)
- Sensitive data (tokens, chat IDs) masked in logs

### Input Validation
- Telegram credentials validated (bot token, chat ID, topic ID formats)
- Session names sanitized to alphanumeric, underscore, hyphen only
- Path traversal attacks prevented (scripts validated to be within CLAUDE_HOME)

### Command Injection Prevention
- No `shell=True` in subprocess calls
- Arguments parsed with `shlex.split()` for safe tokenization
- tmux input sanitized (ANSI escapes, control characters filtered)
- Variable substitution uses `awk` instead of `sed` (prevents injection)

### Session Isolation
- Each listener only processes messages from its configured topic
- Messages from unauthorized chats/topics are ignored
- Safe environment variable whitelist (dangerous vars like LD_PRELOAD excluded)

### Local Processing
- All communication stays local (no cloud servers)
- Listener runs on your machine, not Telegram's servers
- Bot token never leaves your system except for Telegram API calls

## License

MIT - Use freely!
