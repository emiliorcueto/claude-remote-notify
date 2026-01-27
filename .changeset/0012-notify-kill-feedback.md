---
"claude-remote-notify": patch
---

Fix /notify kill provides no feedback

- Handle kill command directly in Python instead of via shell script
- Send confirmation message ("🛑 Listener shutting down") before exit
- Gracefully cleanup media files and PID file before exiting
