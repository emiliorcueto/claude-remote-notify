---
"claude-remote-notify": minor
---

Add smart notification context parsing for cleaner Telegram messages.

Notifications now extract only natural language text (questions, summaries, options, bullets) from terminal output. Code blocks, diffs, file paths, and prompt lines are automatically omitted. Messages display as plain text instead of monospace `<pre>` blocks, improving readability on mobile.

Key features:
- Line classification: CODE, DIFF, FILE_PATH, PROMPT, OPTION, BULLET, TEXT
- Backwards extraction from most recent content
- Graceful fallback to `<pre>` block when parser unavailable
- Removes timestamp from notifications (Telegram already shows message time)
