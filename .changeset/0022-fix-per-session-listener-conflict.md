---
"claude-remote-notify": patch
---

Fix Telegram messages being silently dropped when more than one `claude-remote` session is running. `claude-remote` and `hooks/remote-notify.sh` now ensure a single multi-session listener handles every session instead of spawning one per session — per-session listeners conflicted on the shared bot token (`getUpdates` is single-consumer), and topic-mismatched messages were filtered out before the intended listener could see them. The fix also keeps the listener alive across `claude-remote --kill <session>` so other sessions are unaffected. (Issue #37)
