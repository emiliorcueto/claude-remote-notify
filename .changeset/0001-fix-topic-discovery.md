---
"claude-remote-notify": minor
---

Improve setup script and topic discovery UX

- Setup script allows creating multiple session configs in one run
- Re-running setup detects existing install, offers to add sessions
- Add --force flag for full reinstall
- Fix pipe/heredoc bug causing JSON parse error on empty stdin
- Add --poll mode for real-time message watching
- Add --debug flag to show raw API response
- Add webhook detection and automatic removal
- Add bot token verification step
- Add auto-install option for missing dependencies (brew/apt + pip)
- Use pip --user instead of --break-system-packages
- Update docs: Group Privacy setup, bot re-add requirement after privacy change
