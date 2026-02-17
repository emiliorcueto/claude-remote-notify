---
"claude-remote-notify": patch
---

Fix /preview doubled response - remove intermediary "Generating preview..." message; only the 👀 reaction and HTML file are sent. Add configurable notification debounce (NOTIFY_DEBOUNCE, default 20s) - notifications are delayed to avoid spamming when user is at the terminal.
