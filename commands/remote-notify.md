---
description: Control notifications and the shared multi-session Telegram listener for Claude Remote
argument-hint: "on|off|status|config|start|kill|help"
allowed-tools: Bash(~/.claude/hooks/remote-notify.sh:*)
model: haiku
---
# Remote Notification Control

Manage Telegram notifications and the multi-session Telegram listener.

> **Note:** The listener is shared across every `claude-remote` session on this host (one process polls Telegram and routes by topic ID — see issue #37). `start` and `kill` therefore affect every session. Use `on` / `off` to silence outbound notifications for the current session without touching the listener.

## Commands

| Command | Description |
|---------|-------------|
| `/remote-notify on` | Enable outbound notifications for this session |
| `/remote-notify off` | Disable outbound notifications for this session (listener keeps running) |
| `/remote-notify status` | Check notification + shared listener state |
| `/remote-notify config` | Show full configuration |
| `/remote-notify start` | Start the shared multi-session Telegram listener (idempotent — no-op if already running) |
| `/remote-notify kill` | Stop the shared multi-session listener — **affects every claude-remote session on this host** |
| `/remote-notify help` | Show detailed help |

## Executing

!`~/.claude/hooks/remote-notify.sh $ARGUMENTS 2>&1`
