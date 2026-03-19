---
"claude-remote-notify": patch
---

Fix multi-session Telegram routing: prevent duplicate message processing when old single-session listeners conflict with multi-session listener. Added PID-based startup guard, persistent update deduplication, and cleanup script for old listeners.
