---
"claude-remote-notify": minor
---

Add photo and document support via Telegram

- Photos downloaded and injected as `[Image: /path]`
- Documents downloaded and injected as `[Document: /path]`
- Captions included with media
- Unsupported media (voice, video, stickers) returns friendly error
- Files stored in `/tmp/claude-telegram/` with session prefix
- Automatic cleanup on session exit
