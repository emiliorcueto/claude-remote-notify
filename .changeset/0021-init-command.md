---
"claude-remote-notify": patch
---

Add `claude-remote init` action for one-shot session bootstrap: auto-creates a Telegram forum topic (with deterministic icon color), writes the session config, sends a minimal welcome message, and launches the session. Supports flag-driven non-interactive use and name-based topic reuse via a local registry.
