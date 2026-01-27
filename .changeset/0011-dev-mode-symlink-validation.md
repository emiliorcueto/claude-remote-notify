---
"claude-remote-notify": patch
---

Fix dev mode symlinks blocked by script path security validation

- Allow symlinks within CLAUDE_HOME to point to targets outside (dev mode)
- Validate symlink location first, then check target's ownership and permissions
- Target must still be user-owned and not world-writable for security
- Handle macOS path symlinks (/var -> /private/var) in path comparison
