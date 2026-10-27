---
"claude-remote-notify": patch
---

Fix `/preview N` ignoring the requested line count. The capture is now trimmed to the last N lines (trailing blank rows excluded), and when fewer lines exist — e.g. Claude Code's fullscreen TUI, which leaves tmux with no scrollback — the caption reports the actual vs requested count and why. Non-numeric or zero counts are rejected. (Issue #41)
