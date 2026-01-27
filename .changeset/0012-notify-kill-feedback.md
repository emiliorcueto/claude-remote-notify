---
"claude-remote-notify": patch
---

Replace /notify kill with /notify stop (pause mode)

- Rename /notify kill to /notify stop
- Stop pauses listener instead of terminating (can resume with /notify start)
- /notify start resumes paused listener
- When paused, listener only responds to /notify start (ignores other messages)
- Enables remote listener control via Telegram without losing the process
