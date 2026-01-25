---
"claude-remote-notify": patch
---

Fix get-topic-ids.sh script failures and improve topic discovery UX

- Fix pipe/heredoc bug causing JSON parse error on empty stdin
- Add --poll mode for real-time message watching
- Add --debug flag to show raw API response
- Add webhook detection and automatic removal
- Add bot token verification step
- Update docs: Group Privacy setup, bot re-add requirement after privacy change
