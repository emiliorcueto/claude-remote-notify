---
"claude-remote-notify": patch
---

fix: security hardening (tmux sanitization, error handling, permissions)

- Add tmux input sanitization to filter ANSI escapes and control characters
- Add curl error handling with logging to notify-errors.log
- Add URL encoding functions (urlencode, urlencode_shell)
- Fix file permission race using umask subshell for cleanup scripts
