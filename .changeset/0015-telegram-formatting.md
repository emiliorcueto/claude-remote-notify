---
"claude-remote-notify": minor
---

Add HTML message formatting and inline keyboard buttons for Telegram.

All outgoing messages now use Telegram HTML parse_mode with bold headers, code blocks, and pre-formatted terminal output. When notifications contain numbered options (1., 2., etc.), inline keyboard buttons appear so users can tap instead of typing. Button clicks inject the option number into the correct tmux session.

Key features:
- HTML formatting for all command responses (/status, /help, /ping, etc.)
- HTML formatting for notification hook messages (telegram-notify.sh)
- Inline keyboard buttons when 2+ numbered options detected
- callback_query handling in both single-session and multi-session modes
- escape_html() for safe user-generated content
- html_escape() bash function in lib/common.sh
- Backwards compatible: falls back to plain curl if Python unavailable
