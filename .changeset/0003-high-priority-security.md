---
"claude-remote-notify": patch
---

fix: high priority security vulnerabilities

- Add safe config loading (load_config_safely) - validates ownership, rejects world-writable, parses instead of sourcing
- Mask sensitive data in logs - bot token and chat ID now properly masked
- Add input validation for Telegram credentials (bot token, chat ID, topic ID formats)
- Use silent input (-s) for token entry in get-topic-ids.sh
- Add validation functions to lib/common.sh (validate_bot_token, validate_chat_id, mask_sensitive)
