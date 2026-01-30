# Changelog

## [Unreleased]

### Added
- Topic ID as alternative session identifier (Issue #27)
  - `claude-remote 70` resolves topic ID to session name
  - Session names take priority over topic IDs when ambiguous
  - Clear errors for unknown or duplicate topic IDs
  - `resolve_session_identifier()` in lib/common.sh
- Smart notification context parsing (Issue #25)
  - Extracts natural language text from terminal context (questions, summaries, options, bullets)
  - Omits code blocks, diffs, file paths, and prompt lines
  - Line classification: CODE, DIFF, FILE_PATH, PROMPT, OPTION, BULLET, TEXT, EMPTY
  - Code signals: `{}[]();`, keywords (`import`, `def`, `class`, `function`, `const`, `let`, `var`, `return`, `if`, `else`, `for`, `while`), operators (`=>`, `->`, `&&`, `||`)
  - Backwards extraction from most recent content
  - Graceful fallback to `<pre>` block when parser unavailable
  - Removes timestamp from notifications (Telegram already shows message time)
- HTML message formatting + inline keyboard buttons (Issue #24)
  - All outgoing messages use Telegram HTML parse_mode (bold headers, code blocks, pre-formatted output)
  - Inline keyboard buttons when 2+ numbered options detected in notifications
  - Button clicks inject option number into correct tmux session
  - `escape_html()` Python utility and `html_escape()` bash function
  - `callback_query` handling in both single-session and multi-session modes
  - Backwards compatible: falls back to plain curl if Python unavailable
- Multi-session Telegram listener (Issue #22)
  - Single listener process polls Telegram once, routes by topic ID
  - Eliminates "terminated by other getUpdates request" API conflicts
  - Per-session pause state (`/notify stop`/`start`)
  - Hot-reload of session configs (60s scan interval)
  - Graceful cleanup when sessions are removed
  - New `--list` flag to show configured sessions
  - Backwards compatible `--session` flag for single-session mode
- Photo and document support via Telegram (Issue #1)
  - Photos downloaded and injected as `[Image: /path]`
  - Documents downloaded and injected as `[Document: /path]`
  - Captions included with media
  - Unsupported media (voice, video, stickers) returns friendly error
  - Files stored in `/tmp/claude-telegram/` with session prefix
  - Automatic cleanup on session exit
- `/clear` and `/compact` commands via Telegram to manage Claude context remotely
- Unit tests for command handlers (62 tests covering notify on/off toggle scenarios)
- Telegram message formatting: strip ANSI codes, convert tables to bullet points for readability
- `format_for_telegram()` function in lib/common.sh for terminal output transformation

### Fixed
- Fix `/preview` command issues (Issue #20)
  - Add emoji reaction (👀 on success, 😱 on error)
  - Fix HTML file not rendering in Telegram (mktemp was adding suffix after .html)
  - Use temp directory with proper `.html` filename for Telegram compatibility
  - Fix heredoc replacing stdin, causing terminal content to be lost

### Changed
- Replace `/notify kill` with `/notify stop` (pause mode) (Issue #18)
  - `/notify stop` pauses listener instead of terminating
  - `/notify start` resumes paused listener
  - When paused, only `/notify start` is processed (other messages ignored)
  - Enables remote listener control via Telegram without losing the process
- Fix dev mode symlinks blocked by security validation (Issue #16)
  - Allow symlinks within CLAUDE_HOME to point to targets outside (dev mode setup)
  - Validate symlink location, then check target's ownership and permissions
  - Target must still be user-owned and not world-writable for security
- Fix `/notify on` not working after `/notify off` via Telegram (Issue #12)
  - Handle on/off commands directly in Python listener instead of delegating to shell script
  - Eliminates subprocess environment issues that prevented flag file creation
  - Listener now sends confirmation messages directly for reliable feedback
- Fix touchpad scroll cycling through prompt history instead of conversation history
  - Enable tmux mouse mode for claude-remote sessions
  - Add text selection hint (Option+drag on Mac) to session startup output
  - Fix mouse mode not applied when reattaching to existing session

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
