---
"claude-remote-notify": minor
---

Add multi-session Telegram listener support.

Single listener process now polls Telegram once and routes messages to the correct tmux session based on topic ID. This eliminates "terminated by other getUpdates request" conflicts when running multiple sessions with the same bot token.

Key features:
- Single `getUpdates` call handles all sessions (no API conflicts)
- Messages routed by topic ID to correct tmux session
- Per-session pause state (`/notify stop`/`start`)
- Hot-reload of session configs (60s scan interval)
- Graceful cleanup when sessions are removed
- Backwards compatible `--session` flag for single-session mode
- New `--list` flag to show configured sessions

Usage:
- Multi-session (default): `telegram-listener.py`
- Single-session: `telegram-listener.py --session NAME`
- List sessions: `telegram-listener.py --list`
