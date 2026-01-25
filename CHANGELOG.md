# Changelog

## [Unreleased]

### Fixed
- Fix get-topic-ids.sh JSON parse error caused by pipe/heredoc stdin conflict
- Add webhook detection - webhooks block getUpdates, now auto-removed

### Added
- `--poll` mode for real-time message watching while sending test messages
- `--debug` flag to show raw Telegram API response
- Bot token verification before fetching updates

### Documentation
- Restructure Quick Start: separate bot creation from group setup
- Add explicit Group Privacy disable instructions with @BotFather commands
- Document critical requirement to remove/re-add bot after changing privacy setting
- Add new troubleshooting section for "only /commands work" issue
- Add --poll usage to Topic ID discovery instructions
- Clarify @mentions don't work in forum groups with privacy enabled
