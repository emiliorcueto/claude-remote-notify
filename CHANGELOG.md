# Changelog

## [Unreleased]

### Security
- Fix command injection in telegram-listener.py - removed shell=True, use shlex for arg parsing, whitelist safe env vars
- Fix sed injection in claude-remote - replaced sed with awk for safe placeholder substitution
- Fix insecure temp files in telegram-preview.sh - use mktemp with cleanup trap
- Add safe config loading (load_config_safely) - validates ownership, rejects world-writable, parses instead of sourcing
- Mask sensitive data in logs - bot token and chat ID now properly masked
- Add input validation for Telegram credentials (bot token, chat ID, topic ID formats)
- Use silent input (-s) for token entry in get-topic-ids.sh
- Add tmux input sanitization - filter ANSI escapes and control characters to prevent terminal injection
- Add curl error handling - log failures to notify-errors.log
- Add URL encoding functions (urlencode, urlencode_shell) for safe URL parameter handling
- Fix file permission race - use umask subshell when creating cleanup scripts

### Added
- Shared security library lib/common.sh with safe temp file handling, variable substitution, input validation
- Validation functions: validate_bot_token, validate_chat_id, validate_topic_id, mask_sensitive
- sanitize_tmux_input() - filters ANSI escapes and control characters
- urlencode/urlencode_shell - URL encoding functions
- Unit tests for security functions (96% Python, shell tests passing)

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
