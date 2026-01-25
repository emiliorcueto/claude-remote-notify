---
description: Control notifications and listener for Claude Remote
argument-hint: "on|off|status|config|start|kill|help"
allowed-tools: Bash(~/.claude/hooks/remote-notify.sh:*)
model: haiku
---
# Remote Notification Control

Manage Telegram notifications and the remote listener.

## Commands

| Command | Description |
|---------|-------------|
| `/remote-notify on` | Enable notifications |
| `/remote-notify off` | Disable notifications |
| `/remote-notify status` | Check notification/listener state |
| `/remote-notify config` | Show full configuration |
| `/remote-notify start` | Start Telegram listener |
| `/remote-notify kill` | Stop Telegram listener |
| `/remote-notify help` | Show detailed help |

## Executing

!`~/.claude/hooks/remote-notify.sh $ARGUMENTS 2>&1`
