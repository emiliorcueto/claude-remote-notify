# Changelog

## [Unreleased]

### Fixed
- Fix Telegram messages not submitting to Claude (Enter key was interpreted as text)
- Use tmux send-keys `-l` (literal) mode for proper multi-line message support
- Fix setup script not updating hooks/scripts when already installed
- Fix get-topic-ids.sh JSON parse error caused by pipe/heredoc stdin conflict
- Add webhook detection - webhooks block getUpdates, now auto-removed
- Fix PATH setup for different shells (zsh, bash, fish) and OS (macOS, Linux)
- Export PATH in current session so commands work immediately after setup

### Changed
- Exiting Claude now automatically kills listener and tmux session (no manual cleanup needed)
- Replace "Sent" confirmation message with 👀 emoji reaction on user's message
- On failure: react with 😱 and send error message

### Added
- Setup script now allows creating multiple session configs in one run
- Re-running setup detects existing install, offers to add sessions or reinstall
- `--force` flag to force full reinstall
- Auto-install option for missing dependencies in setup script (brew/apt + pip)
- Use `pip install --user` instead of `--break-system-packages` (cleaner, no system modification)
- `--poll` mode for real-time message watching while sending test messages
- `--debug` flag to show raw Telegram API response
- Bot token verification before fetching updates

### Documentation
- Clarify claude-remote commands: default session, named sessions, --list behavior
- Explain session name vs Topic ID relationship
- Restructure Quick Start: separate bot creation from group setup
- Add explicit Group Privacy disable instructions with @BotFather commands
- Document critical requirement to remove/re-add bot after changing privacy setting
- Add new troubleshooting section for "only /commands work" issue
- Add --poll usage to Topic ID discovery instructions
- Clarify @mentions don't work in forum groups with privacy enabled
