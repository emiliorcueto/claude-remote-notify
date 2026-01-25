---
"claude-remote-notify": patch
---

fix: critical security vulnerabilities

- Fix command injection in telegram-listener.py by removing shell=True, using shlex for arg parsing, and whitelisting safe environment variables
- Fix sed injection in claude-remote by replacing sed with awk for safe placeholder substitution
- Fix insecure temp files in telegram-preview.sh by using mktemp with cleanup trap
- Add shared security library lib/common.sh with safe temp file handling, variable substitution, and input validation functions
