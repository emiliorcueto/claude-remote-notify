---
description: Send terminal output to Telegram WITH FULL COLORS
argument-hint: "[N] | [back N] | [help]"
allowed-tools: Bash(~/.claude/hooks/telegram-preview.sh:*)
model: haiku
---
# Preview Output on Telegram (With Colors!)

Send the current terminal output to your Telegram as a styled HTML document.
**Colors, code diffs, and formatting are fully preserved!**

## Arguments

| Argument | Description |
|----------|-------------|
| `/remote-preview-output` | Send last 50 lines |
| `/remote-preview-output 100` | Send last 100 lines |
| `/remote-preview-output back 0` | Current response only |
| `/remote-preview-output back 1` | Previous exchange |
| `/remote-preview-output help` | Show help with all arguments |

## Executing

!`~/.claude/hooks/telegram-preview.sh $ARGUMENTS 2>&1`
