---
"claude-remote-notify": patch
---

Fix /preview command issues

- Add emoji reaction (👀 on success, 😱 on error) for /preview command
- Fix HTML file not rendering in Telegram (mktemp was adding suffix after .html)
- Use temp directory with proper .html filename for Telegram compatibility
- Fix heredoc replacing stdin causing terminal content to be lost
