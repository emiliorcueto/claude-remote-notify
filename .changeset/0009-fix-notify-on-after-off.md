---
"claude-remote-notify": patch
---

Fix `/notify on` not working after `/notify off` via Telegram

- Handle `/notify on` and `/notify off` commands directly in Python listener
- Eliminates subprocess environment issues that prevented flag file creation
- Listener now sends confirmation messages directly (previously relied on shell script)
- Add comprehensive unit tests for notify on/off toggle scenarios
