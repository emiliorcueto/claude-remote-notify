#!/usr/bin/env python3
"""
=============================================================================
telegram-listener.py - Multi-Session Telegram Listener with Topics Support
=============================================================================

This listener handles messages from a specific Telegram Topic (thread) and
routes them to the corresponding tmux session.

For multi-session setups:
  - Create a Telegram Group with Topics (Forum) enabled
  - Create one topic per Claude session
  - Run one listener per session, each configured with its topic ID

Usage:
  telegram-listener.py [--session NAME]

Environment:
  CLAUDE_SESSION - Session name (default: "default")

Telegram Commands:
  /help              - Show all commands
  /status            - Session status + recent output
  /ping              - Test connectivity
  /clear             - Clear Claude context
  /compact           - Compact Claude context
  /preview [N]       - Send terminal output (default 50 lines)
  /preview back N    - Send Nth previous exchange
  /preview help      - Preview help
  /notify on|off     - Toggle notifications
  /notify status     - Notification state
  /notify config     - Full configuration
  /notify start|stop - Listener control
  /notify help       - Notify help
  (any text)         - Sent to Claude

Media Support:
  Photos             - Downloaded, injected as [Image: /path]
  Documents          - Downloaded, injected as [Document: /path]
  Voice/Video/etc    - Not supported (user notified)

=============================================================================
"""

import os
import sys
import time
import subprocess
import signal
import argparse
import re
import shlex
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List

try:
    import requests
except ImportError:
    print("ERROR: 'requests' module not found")
    print("Install with: pip install --user requests")
    sys.exit(1)


# =============================================================================
# HTML FORMATTING
# =============================================================================

# Regex for detecting numbered options in terminal output
# [>\u276f\u203a] matches ASCII > and Unicode cursor chars (❯ ›) used by CLI tools
OPTION_PATTERN = re.compile(
    r'^\s*[>\u276f\u203a]?\s*(?:(\d+)[.\)]\s+|#(\d+)\s+|\((\d+)\)\s+)(.+)$',
    re.MULTILINE
)


def escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram parse_mode=HTML."""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# =============================================================================
# MULTI-SESSION DATA STRUCTURES
# =============================================================================

@dataclass
class SessionState:
    """Per-session configuration and runtime state."""
    name: str
    topic_id: str
    tmux_session: str
    chat_id: str
    bot_token: str
    paused: bool = False
    config_path: Optional[Path] = None
    config_mtime: float = 0


class SessionManager:
    """Central manager for all configured sessions."""

    def __init__(self, claude_home: Path):
        self.claude_home = claude_home
        self.sessions_dir = claude_home / 'sessions'
        self.sessions: Dict[str, SessionState] = {}  # topic_id -> session
        self.bot_token: Optional[str] = None
        self.chat_id: Optional[str] = None
        self.last_scan_time: float = 0

    def scan_configs(self) -> bool:
        """Scan ~/.claude/sessions/*.conf, validate, populate sessions dict.

        Returns True if at least one valid session was found.

        Validation rules:
        - All sessions must have same TELEGRAM_BOT_TOKEN
        - All sessions must have same TELEGRAM_CHAT_ID
        - Topic IDs must be unique across sessions
        - Config files must be user-owned, not world-writable
        """
        if not self.sessions_dir.exists():
            return False

        new_sessions: Dict[str, SessionState] = {}
        found_bot_token: Optional[str] = None
        found_chat_id: Optional[str] = None
        seen_topics: set = set()

        for config_file in sorted(self.sessions_dir.glob('*.conf')):
            try:
                # Security check: file ownership and permissions
                stat_info = config_file.stat()
                if stat_info.st_uid not in (os.getuid(), 0):
                    log_multi(f"Skipping {config_file.name}: not owned by current user", "WARN")
                    continue
                if stat_info.st_mode & 0o002:
                    log_multi(f"Skipping {config_file.name}: world-writable", "WARN")
                    continue

                config = load_session_config(config_file)
                if not config:
                    continue

                bot_token = config.get('TELEGRAM_BOT_TOKEN', '')
                chat_id = config.get('TELEGRAM_CHAT_ID', '')
                topic_id = config.get('TELEGRAM_TOPIC_ID', '')
                session_name = config_file.stem  # filename without .conf

                # Validate required fields
                if not bot_token or not chat_id:
                    log_multi(f"Skipping {session_name}: missing bot token or chat ID", "WARN")
                    continue

                if not topic_id:
                    log_multi(f"Skipping {session_name}: no topic ID (required for multi-session)", "WARN")
                    continue

                # Validate same bot token across all sessions
                if found_bot_token is None:
                    found_bot_token = bot_token
                elif bot_token != found_bot_token:
                    log_multi(f"Skipping {session_name}: different bot token", "WARN")
                    continue

                # Validate same chat ID across all sessions
                if found_chat_id is None:
                    found_chat_id = chat_id
                elif chat_id != found_chat_id:
                    log_multi(f"Skipping {session_name}: different chat ID", "WARN")
                    continue

                # Validate unique topic ID
                if topic_id in seen_topics:
                    log_multi(f"Skipping {session_name}: duplicate topic ID {topic_id}", "WARN")
                    continue
                seen_topics.add(topic_id)

                # Get tmux session name
                tmux_session = config.get('TMUX_SESSION', f'claude-{session_name}')

                # Check if we already have this session (preserve pause state)
                existing = self.sessions.get(topic_id)
                paused = existing.paused if existing else False

                new_sessions[topic_id] = SessionState(
                    name=session_name,
                    topic_id=topic_id,
                    tmux_session=tmux_session,
                    chat_id=chat_id,
                    bot_token=bot_token,
                    paused=paused,
                    config_path=config_file,
                    config_mtime=stat_info.st_mtime
                )

            except Exception as e:
                log_multi(f"Error loading {config_file}: {e}", "ERROR")
                continue

        # Detect removed sessions and clean up
        removed = set(self.sessions.keys()) - set(new_sessions.keys())
        for topic_id in removed:
            session = self.sessions[topic_id]
            log_multi(f"Session removed: {session.name}")
            cleanup_media_files_for_session(session.name)

        # Update state
        self.sessions = new_sessions
        self.bot_token = found_bot_token
        self.chat_id = found_chat_id
        self.last_scan_time = time.time()

        if new_sessions:
            log_multi(f"Loaded {len(new_sessions)} session(s): {', '.join(s.name for s in new_sessions.values())}")

        return len(new_sessions) > 0

    def get_session_by_topic(self, topic_id: str) -> Optional[SessionState]:
        """Get session by topic ID."""
        return self.sessions.get(topic_id)

    def set_paused(self, session_name: str, paused: bool) -> bool:
        """Update pause state for a session by name."""
        for session in self.sessions.values():
            if session.name == session_name:
                session.paused = paused
                return True
        return False

    def get_session_by_name(self, name: str) -> Optional[SessionState]:
        """Get session by name."""
        for session in self.sessions.values():
            if session.name == name:
                return session
        return None


def load_session_config(config_path: Path) -> Dict[str, str]:
    """Load single session config file, return dict of key=value pairs."""
    config = {}
    if config_path.exists():
        with open(config_path) as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    value = value.strip().strip('"').strip("'")
                    config[key.strip()] = value
    return config


def log_multi(message: str, level: str = "INFO"):
    """Log message for multi-session listener."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp}] [multi] [{level}] {message}"
    print(log_line)

    try:
        log_file = CLAUDE_HOME / 'logs' / 'listener-multi.log'
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'a') as f:
            f.write(log_line + '\n')
    except Exception:
        pass


def cleanup_media_files_for_session(session_name: str):
    """Remove media files for a specific session."""
    media_dir = Path('/tmp/claude-telegram')
    if not media_dir.exists():
        return

    pattern = f"{session_name}-*"
    try:
        for f in media_dir.glob(pattern):
            try:
                f.unlink()
                log_multi(f"Cleaned up: {f}")
            except Exception as e:
                log_multi(f"Failed to clean up {f}: {e}", "WARN")
    except Exception as e:
        log_multi(f"Error during media cleanup: {e}", "WARN")

# =============================================================================
# CONFIGURATION
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description='Telegram listener for Claude sessions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  Multi-session (default):
    telegram-listener.py
    - Polls Telegram once, routes to all sessions by topic ID
    - Requires ~/.claude/sessions/*.conf with TELEGRAM_TOPIC_ID

  Single-session (legacy):
    telegram-listener.py --session NAME
    - One listener per session (may cause API conflicts with multiple)

  List sessions:
    telegram-listener.py --list
"""
    )
    parser.add_argument('--session', '-s', default=None,
                        help='Run in single-session mode for NAME (legacy)')
    parser.add_argument('--list', '-l', action='store_true',
                        help='List all configured sessions and exit')
    parser.add_argument('--multi', '-m', action='store_true',
                        help='Force multi-session mode (default when no --session)')
    return parser.parse_args()


# Only parse args when run as main script (not when imported)
if __name__ == '__main__':
    args = parse_args()
    MULTI_SESSION_MODE = args.multi or (args.session is None and not args.list)
    SESSION_NAME = args.session or os.environ.get('CLAUDE_SESSION', 'default')
else:
    # Default values for imports/testing
    args = None
    MULTI_SESSION_MODE = False
    SESSION_NAME = os.environ.get('CLAUDE_SESSION', 'default')

CLAUDE_HOME = Path(os.environ.get('CLAUDE_HOME', Path.home() / '.claude'))
SESSIONS_DIR = CLAUDE_HOME / 'sessions'
CONFIG_FILE = SESSIONS_DIR / f'{SESSION_NAME}.conf'
GLOBAL_CONFIG = CLAUDE_HOME / 'telegram-remote.conf'

def load_config():
    """Load config from session file or global fallback"""
    config = {}
    config_path = CONFIG_FILE if CONFIG_FILE.exists() else GLOBAL_CONFIG
    
    if config_path.exists():
        with open(config_path) as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    value = value.strip().strip('"').strip("'")
                    config[key.strip()] = value
    return config

config = load_config()

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', config.get('TELEGRAM_BOT_TOKEN', ''))
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', config.get('TELEGRAM_CHAT_ID', ''))
TOPIC_ID = os.environ.get('TELEGRAM_TOPIC_ID', config.get('TELEGRAM_TOPIC_ID', ''))
TMUX_SESSION = os.environ.get('TMUX_SESSION', config.get('TMUX_SESSION', f'claude-{SESSION_NAME}'))

POLL_TIMEOUT = 30
LOG_FILE = CLAUDE_HOME / 'logs' / f'listener-{SESSION_NAME}.log'
PID_FILE = CLAUDE_HOME / 'pids' / f'listener-{SESSION_NAME}.pid'

# Whitelisted environment variables for subprocess execution
SAFE_ENV_VARS = {'PATH', 'HOME', 'USER', 'SHELL', 'LANG', 'TERM', 'TMPDIR', 'LC_ALL', 'LC_CTYPE'}

# Listener pause state (for /notify stop/start)
listener_paused = False


def get_safe_env():
    """Return environment dict with only safe variables plus session-specific ones."""
    env = {k: v for k, v in os.environ.items() if k in SAFE_ENV_VARS}
    env['CLAUDE_SESSION'] = SESSION_NAME
    env['TMUX_SESSION'] = TMUX_SESSION
    env['CLAUDE_HOME'] = str(CLAUDE_HOME)
    return env


def validate_script_path(script_path):
    """Validate script path is within CLAUDE_HOME and has safe permissions.

    For symlinks within CLAUDE_HOME (dev mode), validates the target separately.
    """
    path = Path(script_path)
    claude_home_resolved = CLAUDE_HOME.resolve()

    # First check: the path (or symlink) must be within CLAUDE_HOME
    # Resolve parent to handle path symlinks (e.g., /var -> /private/var on macOS)
    # but keep the script name unresolved to preserve symlink detection
    script_parent_resolved = path.parent.resolve()
    script_abs = script_parent_resolved / path.name
    if not str(script_abs).startswith(str(claude_home_resolved)):
        raise ValueError(f"Script path {script_abs} is outside CLAUDE_HOME")

    # Script/symlink must exist
    if not path.exists():
        raise ValueError(f"Script not found: {path}")

    # Handle symlinks within CLAUDE_HOME (dev mode)
    if path.is_symlink():
        target = path.resolve()
        # Validate target exists and is a file
        if not target.exists():
            raise ValueError(f"Symlink target not found: {target}")
        if not target.is_file():
            raise ValueError(f"Symlink target is not a file: {target}")
        stat_info = target.stat()
    else:
        # Regular file - must be a file
        if not path.is_file():
            raise ValueError(f"Not a file: {path}")
        stat_info = path.stat()

    # Security checks on the actual file (or symlink target)
    # Must be owned by current user or root
    if stat_info.st_uid not in (os.getuid(), 0):
        raise ValueError(f"Script not owned by current user or root: {path}")

    # Script must not be world-writable
    if stat_info.st_mode & 0o002:
        raise ValueError(f"Script is world-writable: {path}")

    return path.resolve()


def mask_sensitive(value, show_start=3, show_end=2):
    """Mask sensitive string for safe logging.

    Args:
        value: The string to mask
        show_start: Number of chars to show at start (default 3)
        show_end: Number of chars to show at end (default 2)

    Returns:
        Masked string like "abc...xy"
    """
    if not value:
        return "(not set)"
    value = str(value)
    if len(value) <= show_start + show_end + 3:
        return "***"
    return f"{value[:show_start]}...{value[-show_end:]}"

# =============================================================================
# LOGGING
# =============================================================================

def log(message, level="INFO"):
    """Log message to file and stdout"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp}] [{SESSION_NAME}] [{level}] {message}"
    print(log_line)
    
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'a') as f:
            f.write(log_line + '\n')
    except Exception:
        pass

# =============================================================================
# PID FILE MANAGEMENT
# =============================================================================

def write_pid():
    """Write PID file for this session"""
    try:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
    except Exception as e:
        log(f"Could not write PID file: {e}", "WARN")

def remove_pid():
    """Remove PID file on exit"""
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception:
        pass

# =============================================================================
# TELEGRAM API
# =============================================================================

def get_updates(offset=None):
    """Get updates from Telegram using long polling"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {
        'timeout': POLL_TIMEOUT,
        'allowed_updates': ['message', 'callback_query']
    }
    if offset:
        params['offset'] = offset
    
    try:
        response = requests.get(url, params=params, timeout=POLL_TIMEOUT + 10)
        data = response.json()
        
        if data.get('ok'):
            return data.get('result', [])
        else:
            log(f"API error: {data.get('description', 'Unknown')}", "ERROR")
            return []
    except requests.exceptions.Timeout:
        return []
    except requests.exceptions.ConnectionError:
        log("Connection error - will retry", "WARN")
        return []
    except Exception as e:
        log(f"Error getting updates: {e}", "ERROR")
        return []

def send_message(text, parse_mode=None):
    """Send a message to Telegram (to specific topic if configured)"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': CHAT_ID,
        'text': text
    }
    
    # Add topic ID if configured
    if TOPIC_ID:
        data['message_thread_id'] = TOPIC_ID
    
    if parse_mode:
        data['parse_mode'] = parse_mode
    
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        log(f"Error sending message: {e}", "ERROR")

def send_document(filepath, caption=""):
    """Send a document to Telegram (to specific topic if configured)"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    data = {
        'chat_id': CHAT_ID,
        'caption': caption
    }

    if TOPIC_ID:
        data['message_thread_id'] = TOPIC_ID

    try:
        with open(filepath, 'rb') as f:
            requests.post(url, data=data, files={'document': f}, timeout=30)
    except Exception as e:
        log(f"Error sending document: {e}", "ERROR")

def set_message_reaction(message_id, emoji="👍"):
    """Set a reaction emoji on a message.

    Telegram only allows specific reaction emojis:
    👍 👎 ❤️ 🔥 🥰 👏 😁 🤔 🤯 😱 🤬 😢 🎉 🤩 🤮 💩 🙏 👌 🕊 🤡 🥱 🥴 😍 🐳 ❤️‍🔥 🌚 🌭 💯 🤣 ⚡ 🍌 🏆 💔 🤨 😐 🍓 🍾 💋 🖕 😈 😴 😭 🤓 👻 👨‍💻 👀 🎃 🙈 😇 😨 🤝 ✍️ 🤗 🫡 🎅 🎄 ☃️ 💅 🤪 🗿 🆒 💘 🙉 🦄 😘 💊 🙊 😎 👾 🤷‍♂️ 🤷 🤷‍♀️ 😡

    Pass empty string or None to remove reaction.
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMessageReaction"
    data = {
        'chat_id': CHAT_ID,
        'message_id': message_id,
    }

    if emoji:
        data['reaction'] = [{'type': 'emoji', 'emoji': emoji}]
    else:
        data['reaction'] = []  # Empty array removes reaction

    try:
        response = requests.post(url, json=data, timeout=10)
        result = response.json()
        if not result.get('ok'):
            log(f"Reaction failed: {result.get('description', 'Unknown error')}", "WARN")
            return False
        return True
    except Exception as e:
        log(f"Error setting reaction: {e}", "ERROR")
        return False


# =============================================================================
# MULTI-SESSION TELEGRAM API (session-aware)
# =============================================================================

def get_updates_multi(offset: Optional[int], bot_token: str) -> list:
    """Get updates from Telegram using long polling (multi-session version)."""
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    params = {
        'timeout': POLL_TIMEOUT,
        'allowed_updates': ['message', 'callback_query']
    }
    if offset:
        params['offset'] = offset

    try:
        response = requests.get(url, params=params, timeout=POLL_TIMEOUT + 10)
        data = response.json()

        if data.get('ok'):
            return data.get('result', [])
        else:
            log_multi(f"API error: {data.get('description', 'Unknown')}", "ERROR")
            return []
    except requests.exceptions.Timeout:
        return []
    except requests.exceptions.ConnectionError:
        log_multi("Connection error - will retry", "WARN")
        return []
    except Exception as e:
        log_multi(f"Error getting updates: {e}", "ERROR")
        return []


def send_message_session(session: SessionState, text: str, parse_mode: Optional[str] = None):
    """Send a message to Telegram for a specific session."""
    url = f"https://api.telegram.org/bot{session.bot_token}/sendMessage"
    data = {
        'chat_id': session.chat_id,
        'text': text
    }

    if session.topic_id:
        data['message_thread_id'] = session.topic_id

    if parse_mode:
        data['parse_mode'] = parse_mode

    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        log_multi(f"[{session.name}] Error sending message: {e}", "ERROR")


def send_document_session(session: SessionState, filepath: str, caption: str = ""):
    """Send a document to Telegram for a specific session."""
    url = f"https://api.telegram.org/bot{session.bot_token}/sendDocument"
    data = {
        'chat_id': session.chat_id,
        'caption': caption
    }

    if session.topic_id:
        data['message_thread_id'] = session.topic_id

    try:
        with open(filepath, 'rb') as f:
            requests.post(url, data=data, files={'document': f}, timeout=30)
    except Exception as e:
        log_multi(f"[{session.name}] Error sending document: {e}", "ERROR")


def set_message_reaction_session(session: SessionState, message_id: int, emoji: str = "👍") -> bool:
    """Set a reaction emoji on a message for a specific session."""
    url = f"https://api.telegram.org/bot{session.bot_token}/setMessageReaction"
    data = {
        'chat_id': session.chat_id,
        'message_id': message_id,
    }

    if emoji:
        data['reaction'] = [{'type': 'emoji', 'emoji': emoji}]
    else:
        data['reaction'] = []

    try:
        response = requests.post(url, json=data, timeout=10)
        result = response.json()
        if not result.get('ok'):
            log_multi(f"[{session.name}] Reaction failed: {result.get('description', 'Unknown error')}", "WARN")
            return False
        return True
    except Exception as e:
        log_multi(f"[{session.name}] Error setting reaction: {e}", "ERROR")
        return False


def answer_callback_query(callback_query_id: str, text: str = ""):
    """Acknowledge a callback query (single-session mode)."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
    data = {'callback_query_id': callback_query_id}
    if text:
        data['text'] = text
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        log(f"Error answering callback: {e}", "ERROR")


def answer_callback_query_session(session: SessionState, callback_query_id: str, text: str = ""):
    """Acknowledge a callback query (multi-session mode)."""
    url = f"https://api.telegram.org/bot{session.bot_token}/answerCallbackQuery"
    data = {'callback_query_id': callback_query_id}
    if text:
        data['text'] = text
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        log_session(session, f"Error answering callback: {e}", "ERROR")


def confirm_button_selection(bot_token: str, chat_id: str, message_id: int,
                             original_text: str, selected_label: str):
    """Edit the notification message to confirm which option was selected.

    Removes the inline keyboard and appends a confirmation line.
    """
    confirmed_text = f"{original_text}\n\n\u2705 Replied: {selected_label}"
    data = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': confirmed_text,
        'parse_mode': 'HTML',
    }
    try:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/editMessageText",
            data=data, timeout=10)
    except Exception:
        # Best effort — original message stays if edit fails
        pass


def get_safe_env_session(session: SessionState) -> Dict[str, str]:
    """Return environment dict with only safe variables plus session-specific ones."""
    env = {k: v for k, v in os.environ.items() if k in SAFE_ENV_VARS}
    env['CLAUDE_SESSION'] = session.name
    env['TMUX_SESSION'] = session.tmux_session
    env['CLAUDE_HOME'] = str(CLAUDE_HOME)
    return env


def log_session(session: SessionState, message: str, level: str = "INFO"):
    """Log message for a specific session (writes to multi log)."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp}] [{session.name}] [{level}] {message}"
    print(log_line)

    try:
        log_file = CLAUDE_HOME / 'logs' / 'listener-multi.log'
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'a') as f:
            f.write(log_line + '\n')
    except Exception:
        pass


def tmux_session_exists_for(tmux_name: str) -> bool:
    """Check if a specific tmux session exists."""
    result = subprocess.run(
        ['tmux', 'has-session', '-t', tmux_name],
        capture_output=True
    )
    return result.returncode == 0


def inject_to_tmux_session(session: SessionState, text: str) -> bool:
    """Inject text into a specific tmux session as keyboard input."""
    if not tmux_session_exists_for(session.tmux_session):
        log_session(session, f"tmux session '{session.tmux_session}' not found", "WARN")
        return False

    # Sanitize input
    sanitized_text = sanitize_tmux_input(text)
    if not sanitized_text:
        log_session(session, "Input was empty after sanitization", "WARN")
        return False

    try:
        subprocess.run(
            ['tmux', 'send-keys', '-t', session.tmux_session, '-l', '--', sanitized_text],
            check=True,
            capture_output=True
        )
        subprocess.run(
            ['tmux', 'send-keys', '-t', session.tmux_session, 'Enter'],
            check=True,
            capture_output=True
        )

        log_session(session, f"Injected: {text[:50]}{'...' if len(text) > 50 else ''}")
        return True
    except subprocess.CalledProcessError as e:
        log_session(session, f"Error injecting: {e}", "ERROR")
        return False


def get_tmux_snapshot_session(session: SessionState, lines: int = 10) -> str:
    """Get current terminal content for a session."""
    if not tmux_session_exists_for(session.tmux_session):
        return "Session not running"

    try:
        result = subprocess.run(
            ['tmux', 'capture-pane', '-t', session.tmux_session, '-p', '-S', f'-{lines}'],
            capture_output=True,
            text=True
        )
        return result.stdout.strip() or "(empty)"
    except Exception:
        return "Could not capture"


# =============================================================================
# MEDIA HANDLING
# =============================================================================

MEDIA_TEMP_DIR = Path('/tmp/claude-telegram')
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB Telegram file limit
DOWNLOAD_TIMEOUT = 60  # seconds

# Unsupported media types with user-friendly messages
UNSUPPORTED_MEDIA_TYPES = {
    'voice': 'Voice messages',
    'video': 'Videos',
    'video_note': 'Video notes',
    'audio': 'Audio files',
    'sticker': 'Stickers',
    'animation': 'Animations/GIFs',
}


def ensure_media_dir():
    """Create media temp directory if it doesn't exist."""
    try:
        MEDIA_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        log(f"Failed to create media dir: {e}", "ERROR")
        return False


def sanitize_filename(filename):
    """Remove unsafe characters from filename.

    Allows alphanumeric, underscore, hyphen, and period.
    Preserves file extension.
    """
    if not filename:
        return "unnamed"

    # Split name and extension
    if '.' in filename:
        name, ext = filename.rsplit('.', 1)
        ext = '.' + re.sub(r'[^a-zA-Z0-9]', '', ext)[:10]  # Sanitize extension
    else:
        name = filename
        ext = ''

    # Sanitize name: keep alphanumeric, underscore, hyphen
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)

    # Collapse multiple underscores
    sanitized = re.sub(r'_+', '_', sanitized)

    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')

    # Ensure non-empty
    if not sanitized:
        sanitized = "file"

    # Limit length
    sanitized = sanitized[:100]

    return sanitized + ext


def get_telegram_file(file_id):
    """Get file path from Telegram using file_id.

    Returns dict with 'file_path' on success, or None on failure.
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile"
    params = {'file_id': file_id}

    try:
        response = requests.get(url, params=params, timeout=30)
        data = response.json()

        if data.get('ok'):
            return data.get('result', {})
        else:
            log(f"getFile API error: {data.get('description', 'Unknown')}", "ERROR")
            return None
    except Exception as e:
        log(f"Error getting file info: {e}", "ERROR")
        return None


def download_telegram_file(file_path, local_path):
    """Download file from Telegram servers to local path.

    Args:
        file_path: Telegram file_path from getFile API
        local_path: Local Path object to save to

    Returns:
        True on success, False on failure
    """
    url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

    try:
        response = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
        response.raise_for_status()

        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        log(f"Downloaded: {local_path}")
        return True
    except requests.exceptions.Timeout:
        log(f"Download timeout for {file_path}", "ERROR")
        return False
    except Exception as e:
        log(f"Error downloading file: {e}", "ERROR")
        return False


def cleanup_media_files():
    """Remove session-specific media files from temp directory."""
    if not MEDIA_TEMP_DIR.exists():
        return

    pattern = f"{SESSION_NAME}-*"
    try:
        for f in MEDIA_TEMP_DIR.glob(pattern):
            try:
                f.unlink()
                log(f"Cleaned up: {f}")
            except Exception as e:
                log(f"Failed to clean up {f}: {e}", "WARN")
    except Exception as e:
        log(f"Error during media cleanup: {e}", "WARN")


def handle_media_message(message, message_id):
    """Handle incoming media message (photo or document).

    Args:
        message: Telegram message dict
        message_id: Message ID for reactions

    Returns:
        tuple: (inject_text, success) where inject_text is the text to send to Claude
               or error message, and success indicates if media was processed
    """
    # Check for unsupported media types first
    for media_type, description in UNSUPPORTED_MEDIA_TYPES.items():
        if media_type in message:
            return (f"{description} not supported. Send photos or documents instead.", False)

    # Handle photos
    if 'photo' in message:
        # Get largest photo (last in array)
        photos = message['photo']
        if not photos:
            return ("Empty photo array", False)

        photo = photos[-1]  # Largest size
        file_id = photo.get('file_id')
        file_size = photo.get('file_size', 0)

        if file_size > MAX_FILE_SIZE:
            return (f"Photo too large ({file_size // 1024 // 1024}MB). Max: 20MB", False)

        return _download_and_format(file_id, 'photo', message)

    # Handle documents
    if 'document' in message:
        doc = message['document']
        file_id = doc.get('file_id')
        file_size = doc.get('file_size', 0)
        file_name = doc.get('file_name', 'document')
        mime_type = doc.get('mime_type', '')

        if file_size > MAX_FILE_SIZE:
            return (f"Document too large ({file_size // 1024 // 1024}MB). Max: 20MB", False)

        return _download_and_format(file_id, 'document', message, file_name, mime_type)

    return ("No media found in message", False)


def _download_and_format(file_id, media_type, message, original_filename=None, mime_type=None):
    """Download media and format inject text.

    Args:
        file_id: Telegram file_id
        media_type: 'photo' or 'document'
        message: Original message dict (for caption)
        original_filename: Original filename (for documents)
        mime_type: MIME type (for documents)

    Returns:
        tuple: (inject_text, success)
    """
    # Ensure temp directory exists
    if not ensure_media_dir():
        return ("Failed to create media directory", False)

    # Get file info from Telegram
    file_info = get_telegram_file(file_id)
    if not file_info:
        return ("Failed to get file info from Telegram", False)

    telegram_path = file_info.get('file_path')
    if not telegram_path:
        return ("No file_path in Telegram response", False)

    # Determine local filename
    if original_filename:
        safe_name = sanitize_filename(original_filename)
    else:
        # Extract extension from telegram path or use default
        ext = Path(telegram_path).suffix or '.jpg'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = f"{media_type}_{timestamp}{ext}"

    # Create unique local path with session prefix
    local_filename = f"{SESSION_NAME}-{safe_name}"
    local_path = MEDIA_TEMP_DIR / local_filename

    # Download file
    if not download_telegram_file(telegram_path, local_path):
        return ("Failed to download file", False)

    # Format inject text
    caption = message.get('caption', '').strip()
    if media_type == 'photo':
        inject_text = f"[Image: {local_path}]"
    else:
        inject_text = f"[Document: {local_path}]"

    if caption:
        inject_text += f" {caption}"

    return (inject_text, True)


# =============================================================================
# TMUX INTERACTION
# =============================================================================

def sanitize_tmux_input(text):
    """Sanitize input before sending to tmux.

    Removes:
    - ANSI escape sequences (colors, cursor movement, etc.)
    - OSC sequences (terminal title, etc.)
    - Control characters (except newline and tab)

    This prevents malicious Telegram messages from disrupting the terminal.
    """
    if not text:
        return ""

    # Remove ANSI CSI escape sequences (e.g., colors, cursor movement)
    text = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text)

    # Remove OSC sequences (e.g., terminal title changes)
    text = re.sub(r'\x1b\][^\x07]*\x07', '', text)

    # Remove other escape sequences
    text = re.sub(r'\x1b[^\x1b]*', '', text)

    # Filter control characters (preserve newline and tab)
    result = []
    for char in text:
        if char in '\n\t':
            result.append(char)
        elif ord(char) >= 32:
            # Check unicode category - skip control chars
            cat = unicodedata.category(char)
            if cat not in ('Cc', 'Cf'):
                result.append(char)

    return ''.join(result)


def tmux_session_exists():
    """Check if tmux session exists"""
    result = subprocess.run(
        ['tmux', 'has-session', '-t', TMUX_SESSION],
        capture_output=True
    )
    return result.returncode == 0

def inject_to_tmux(text):
    """Inject text into tmux session as keyboard input.

    Uses -l (literal) flag to handle multi-line text and special characters,
    then sends Enter separately to submit the prompt.

    Input is sanitized to remove ANSI escapes and control characters.
    """
    if not tmux_session_exists():
        log(f"tmux session '{TMUX_SESSION}' not found", "WARN")
        return False

    # Sanitize input to prevent terminal escape sequence injection
    sanitized_text = sanitize_tmux_input(text)

    if not sanitized_text:
        log("Input was empty after sanitization", "WARN")
        return False

    try:
        # Send text literally (handles multi-line, special chars)
        # The '--' prevents text starting with '-' from being parsed as options
        subprocess.run(
            ['tmux', 'send-keys', '-t', TMUX_SESSION, '-l', '--', sanitized_text],
            check=True,
            capture_output=True
        )

        # Send Enter separately to submit the prompt
        subprocess.run(
            ['tmux', 'send-keys', '-t', TMUX_SESSION, 'Enter'],
            check=True,
            capture_output=True
        )

        log(f"Injected: {text[:50]}{'...' if len(text) > 50 else ''}")
        return True
    except subprocess.CalledProcessError as e:
        log(f"Error injecting: {e}", "ERROR")
        return False

def get_tmux_snapshot(lines=10):
    """Get current terminal content for status"""
    if not tmux_session_exists():
        return "Session not running"
    
    try:
        result = subprocess.run(
            ['tmux', 'capture-pane', '-t', TMUX_SESSION, '-p', '-S', f'-{lines}'],
            capture_output=True,
            text=True
        )
        return result.stdout.strip() or "(empty)"
    except Exception:
        return "Could not capture"

# =============================================================================
# MESSAGE FILTERING
# =============================================================================

def should_process_message(message):
    """
    Determine if this listener should process the message.
    
    For Topic-based routing:
    - If TOPIC_ID is set, only process messages from that topic
    - If no TOPIC_ID, process all messages from the chat (single-session mode)
    """
    from_chat = str(message.get('chat', {}).get('id', ''))
    
    # Must be from authorized chat
    if from_chat != str(CHAT_ID):
        return False
    
    # If topic filtering is enabled
    if TOPIC_ID:
        message_topic = str(message.get('message_thread_id', ''))
        if message_topic != str(TOPIC_ID):
            # Message is from a different topic - ignore
            return False
    
    return True

# =============================================================================
# COMMAND HANDLERS
# =============================================================================

def run_script(script_path, args=""):
    """Run a hook script securely and return output.

    Security measures:
    - No shell=True (prevents command injection)
    - Script path validation (must be within CLAUDE_HOME)
    - Safe environment variables only
    - Args parsed with shlex to prevent injection
    """
    try:
        # Validate script path
        validated_path = validate_script_path(script_path)

        # Build command list (no shell=True)
        cmd = [str(validated_path)]
        if args:
            # Use shlex.split to safely parse arguments
            cmd.extend(shlex.split(args))

        result = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=60,
            env=get_safe_env()
        )
        output = result.stdout + result.stderr
        return output.strip() if output.strip() else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Script timed out after 60 seconds"
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error running script: {e}"

def handle_command(command, from_user, message_id=None):
    """Handle bot commands"""
    parts = command.strip().split()
    cmd = parts[0].lower()
    args = ' '.join(parts[1:]) if len(parts) > 1 else ''
    
    # -------------------------------------------------------------------------
    # /status - Session status
    # -------------------------------------------------------------------------
    if cmd == '/status':
        session_status = "✅ Running" if tmux_session_exists() else "❌ Not running"
        snapshot = get_tmux_snapshot(15)

        topic_info = f"\nTopic ID: {TOPIC_ID}" if TOPIC_ID else "\n(No topic filtering)"

        send_message(
            f"📊 <b>[{escape_html(SESSION_NAME)}] Status</b>\n\n"
            f"Session: <code>{escape_html(TMUX_SESSION)}</code>\n"
            f"Status: {session_status}"
            f"{topic_info}\n\n"
            f"<b>Recent output:</b>\n<pre>{escape_html(snapshot[-800:])}</pre>",
            parse_mode='HTML'
        )
        return True

    # -------------------------------------------------------------------------
    # /ping - Connectivity test
    # -------------------------------------------------------------------------
    elif cmd == '/ping':
        send_message(
            f"🏓 <b>[{escape_html(SESSION_NAME)}]</b> Pong! Listener active.",
            parse_mode='HTML'
        )
        return True

    # -------------------------------------------------------------------------
    # /help - Show all commands
    # -------------------------------------------------------------------------
    elif cmd == '/help':
        send_message(
            f"🤖 <b>[{escape_html(SESSION_NAME)}] Commands</b>\n\n"
            "<b>Status</b>\n"
            "/status - Session status + recent output\n"
            "/ping - Test listener connectivity\n"
            "/help - Show this help\n\n"
            "<b>Context</b>\n"
            "/clear - Clear context\n"
            "/compact - Compact context\n\n"
            "<b>Preview</b>\n"
            "/preview - Send last 50 lines (with colors)\n"
            "/preview N - Send last N lines\n"
            "/preview back N - Send Nth previous exchange\n"
            "/preview help - Show preview help\n"
            "/output - Alias for /preview\n\n"
            "<b>Notifications</b>\n"
            "/notify - Show notify help\n"
            "/notify on|off - Toggle notifications\n"
            "/notify status - Check notification state\n"
            "/notify config - Show full configuration\n"
            "/notify start|stop - Listener control\n\n"
            "<b>Media</b>\n"
            "📷 Photos - Downloaded, sent as [Image: /path]\n"
            "📄 Documents - Downloaded, sent as [Document: /path]\n"
            "❌ Voice/Video/Stickers - Not supported\n\n"
            "Any other text is sent directly.",
            parse_mode='HTML'
        )
        return True

    # -------------------------------------------------------------------------
    # /clear - Clear Claude context
    # -------------------------------------------------------------------------
    elif cmd == '/clear':
        if not tmux_session_exists():
            send_message(
                f"❌ <b>[{escape_html(SESSION_NAME)}]</b> tmux session not found",
                parse_mode='HTML'
            )
            return True

        send_message(
            f"🧹 <b>[{escape_html(SESSION_NAME)}]</b> Clearing context...",
            parse_mode='HTML'
        )
        if inject_to_tmux('/clear'):
            log("Clear command sent to Claude")
        else:
            send_message(
                f"❌ <b>[{escape_html(SESSION_NAME)}]</b> Failed to send clear command",
                parse_mode='HTML'
            )
        return True

    # -------------------------------------------------------------------------
    # /compact - Compact Claude context
    # -------------------------------------------------------------------------
    elif cmd == '/compact':
        if not tmux_session_exists():
            send_message(
                f"❌ <b>[{escape_html(SESSION_NAME)}]</b> tmux session not found",
                parse_mode='HTML'
            )
            return True

        send_message(
            f"📦 <b>[{escape_html(SESSION_NAME)}]</b> Compacting context...",
            parse_mode='HTML'
        )
        if inject_to_tmux('/compact'):
            log("Compact command sent to Claude")
        else:
            send_message(
                f"❌ <b>[{escape_html(SESSION_NAME)}]</b> Failed to send compact command",
                parse_mode='HTML'
            )
        return True

    # -------------------------------------------------------------------------
    # /preview - Terminal output preview (runs telegram-preview.sh)
    # -------------------------------------------------------------------------
    elif cmd == '/preview':
        script = CLAUDE_HOME / 'hooks' / 'telegram-preview.sh'

        if not script.exists():
            send_message(
                f"❌ <b>[{escape_html(SESSION_NAME)}]</b> Preview script not found",
                parse_mode='HTML'
            )
            return True

        # Handle /preview help specially - capture and send as message
        if args.lower() == 'help':
            output = run_script(str(script), 'help')
            send_message(
                f"📺 <b>[{escape_html(SESSION_NAME)}] Preview Help</b>\n\n"
                f"<pre>{escape_html(output[:3500])}</pre>",
                parse_mode='HTML'
            )
            return True

        # For actual preview, the script sends the file directly to Telegram
        send_message(
            f"📺 <b>[{escape_html(SESSION_NAME)}]</b> Generating preview...",
            parse_mode='HTML'
        )
        output = run_script(str(script), args)

        # If there was an error (script outputs to stderr), report it
        if 'Error' in output or 'error' in output.lower():
            if message_id:
                set_message_reaction(message_id, "😱")
            send_message(
                f"⚠️ <b>[{escape_html(SESSION_NAME)}]</b> {escape_html(output[:1000])}",
                parse_mode='HTML'
            )
        else:
            # Success - add reaction
            if message_id:
                set_message_reaction(message_id, "👀")

        return True

    # -------------------------------------------------------------------------
    # /notify - Notification control (runs remote-notify.sh)
    # -------------------------------------------------------------------------
    elif cmd == '/notify':
        script = CLAUDE_HOME / 'hooks' / 'remote-notify.sh'

        if not script.exists():
            send_message(
                f"❌ <b>[{escape_html(SESSION_NAME)}]</b> Notify script not found",
                parse_mode='HTML'
            )
            return True

        # Valid subcommands
        valid_subcmds = ['on', 'off', 'status', 'config', 'start', 'stop', 'help']
        subcmd = args.split()[0].lower() if args else 'help'

        if subcmd not in valid_subcmds:
            send_message(
                f"❌ <b>[{escape_html(SESSION_NAME)}]</b> Unknown subcommand: "
                f"<code>{escape_html(subcmd)}</code>\n\n"
                f"Valid: {', '.join(valid_subcmds)}\n"
                "Try: /notify help",
                parse_mode='HTML'
            )
            return True

        # Declare global for pause state (used by stop/start)
        global listener_paused

        # For on/off, handle flag file directly to avoid subprocess env issues
        if subcmd == 'on':
            notify_flag = CLAUDE_HOME / 'notifications-enabled'
            try:
                notify_flag.touch()
                log(f"Notifications enabled (flag: {notify_flag})")
                send_message(
                    f"🔔 <b>[{escape_html(SESSION_NAME)}]</b> Notifications enabled",
                    parse_mode='HTML'
                )
            except Exception as e:
                log(f"Failed to enable notifications: {e}", "ERROR")
                send_message(
                    f"❌ <b>[{escape_html(SESSION_NAME)}]</b> Failed to enable notifications: "
                    f"{escape_html(str(e))}",
                    parse_mode='HTML'
                )
            return True

        if subcmd == 'off':
            notify_flag = CLAUDE_HOME / 'notifications-enabled'
            try:
                notify_flag.unlink(missing_ok=True)
                log(f"Notifications disabled (flag: {notify_flag})")
                send_message(
                    f"🔕 <b>[{escape_html(SESSION_NAME)}]</b> Notifications disabled",
                    parse_mode='HTML'
                )
            except Exception as e:
                log(f"Failed to disable notifications: {e}", "ERROR")
                send_message(
                    f"❌ <b>[{escape_html(SESSION_NAME)}]</b> Failed to disable notifications: "
                    f"{escape_html(str(e))}",
                    parse_mode='HTML'
                )
            return True

        # Handle stop - pause the listener (can be resumed with /notify start)
        if subcmd == 'stop':
            listener_paused = True
            log("Stop command received - listener paused")
            send_message(
                f"⏸️ <b>[{escape_html(SESSION_NAME)}]</b> Listener paused. "
                "Send /notify start to resume.",
                parse_mode='HTML'
            )
            return True

        # Handle start - resume paused listener
        if subcmd == 'start':
            if not listener_paused:
                send_message(
                    f"✅ <b>[{escape_html(SESSION_NAME)}]</b> Listener already running",
                    parse_mode='HTML'
                )
            else:
                listener_paused = False
                log("Start command received - listener resumed")
                send_message(
                    f"▶️ <b>[{escape_html(SESSION_NAME)}]</b> Listener resumed",
                    parse_mode='HTML'
                )
            return True

        output = run_script(str(script), subcmd)

        # Clean up ANSI color codes for Telegram
        output = re.sub(r'\x1b\[[0-9;]*m', '', output)

        # Format response based on subcommand
        if subcmd == 'help':
            send_message(
                f"🔔 <b>[{escape_html(SESSION_NAME)}] Notify Help</b>\n\n"
                f"<pre>{escape_html(output[:3500])}</pre>",
                parse_mode='HTML'
            )
        else:
            send_message(
                f"🔔 <b>[{escape_html(SESSION_NAME)}] {escape_html(subcmd.title())}</b>\n\n"
                f"<pre>{escape_html(output[:2000])}</pre>",
                parse_mode='HTML'
            )

        return True

    # -------------------------------------------------------------------------
    # /output - Alias for /preview
    # -------------------------------------------------------------------------
    elif cmd == '/output':
        # Redirect to /preview handler
        return handle_command(f'/preview {args}', from_user, message_id)

    return False

# =============================================================================
# MAIN LOOP
# =============================================================================

MAX_RESTART_ATTEMPTS = 3
RESTART_DELAY_BASE = 5  # seconds
CONFIG_RESCAN_INTERVAL = 60  # seconds


# =============================================================================
# MULTI-SESSION COMMAND HANDLER
# =============================================================================

def run_script_session(session: SessionState, script_path: str, args: str = "") -> str:
    """Run a hook script securely for a specific session."""
    try:
        validated_path = validate_script_path(script_path)
        cmd = [str(validated_path)]
        if args:
            cmd.extend(shlex.split(args))

        result = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=60,
            env=get_safe_env_session(session)
        )
        output = result.stdout + result.stderr
        return output.strip() if output.strip() else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Script timed out after 60 seconds"
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error running script: {e}"


def handle_command_session(command: str, from_user: str, message_id: int,
                           session: SessionState, manager: SessionManager) -> bool:
    """Handle bot commands for a specific session (multi-session mode)."""
    parts = command.strip().split()
    cmd = parts[0].lower()
    args = ' '.join(parts[1:]) if len(parts) > 1 else ''

    # -------------------------------------------------------------------------
    # /status - Session status
    # -------------------------------------------------------------------------
    if cmd == '/status':
        session_status = "✅ Running" if tmux_session_exists_for(session.tmux_session) else "❌ Not running"
        snapshot = get_tmux_snapshot_session(session, 15)
        paused_info = " (PAUSED)" if session.paused else ""

        send_message_session(session,
            f"📊 <b>[{escape_html(session.name)}] Status{paused_info}</b>\n\n"
            f"Session: <code>{escape_html(session.tmux_session)}</code>\n"
            f"Status: {session_status}\n"
            f"Topic ID: {session.topic_id}\n\n"
            f"<b>Recent output:</b>\n<pre>{escape_html(snapshot[-800:])}</pre>",
            parse_mode='HTML'
        )
        return True

    # -------------------------------------------------------------------------
    # /ping - Connectivity test
    # -------------------------------------------------------------------------
    elif cmd == '/ping':
        send_message_session(session,
            f"🏓 <b>[{escape_html(session.name)}]</b> Pong! Multi-session listener active.",
            parse_mode='HTML'
        )
        return True

    # -------------------------------------------------------------------------
    # /help - Show all commands
    # -------------------------------------------------------------------------
    elif cmd == '/help':
        send_message_session(session,
            f"🤖 <b>[{escape_html(session.name)}] Commands</b>\n\n"
            "<b>Status</b>\n"
            "/status - Session status + recent output\n"
            "/ping - Test listener connectivity\n"
            "/help - Show this help\n\n"
            "<b>Context</b>\n"
            "/clear - Clear context\n"
            "/compact - Compact context\n\n"
            "<b>Preview</b>\n"
            "/preview - Send last 50 lines (with colors)\n"
            "/preview N - Send last N lines\n"
            "/preview back N - Send Nth previous exchange\n"
            "/preview help - Show preview help\n"
            "/output - Alias for /preview\n\n"
            "<b>Notifications</b>\n"
            "/notify - Show notify help\n"
            "/notify on|off - Toggle notifications (global)\n"
            "/notify status - Check notification state\n"
            "/notify config - Show full configuration\n"
            "/notify start|stop - Pause/resume THIS session\n\n"
            "<b>Media</b>\n"
            "📷 Photos - Downloaded, sent as [Image: /path]\n"
            "📄 Documents - Downloaded, sent as [Document: /path]\n"
            "❌ Voice/Video/Stickers - Not supported\n\n"
            "Any other text is sent directly.",
            parse_mode='HTML'
        )
        return True

    # -------------------------------------------------------------------------
    # /clear - Clear Claude context
    # -------------------------------------------------------------------------
    elif cmd == '/clear':
        if not tmux_session_exists_for(session.tmux_session):
            send_message_session(session,
                f"❌ <b>[{escape_html(session.name)}]</b> tmux session not found",
                parse_mode='HTML'
            )
            return True

        send_message_session(session,
            f"🧹 <b>[{escape_html(session.name)}]</b> Clearing context...",
            parse_mode='HTML'
        )
        if inject_to_tmux_session(session, '/clear'):
            log_session(session, "Clear command sent to Claude")
        else:
            send_message_session(session,
                f"❌ <b>[{escape_html(session.name)}]</b> Failed to send clear command",
                parse_mode='HTML'
            )
        return True

    # -------------------------------------------------------------------------
    # /compact - Compact Claude context
    # -------------------------------------------------------------------------
    elif cmd == '/compact':
        if not tmux_session_exists_for(session.tmux_session):
            send_message_session(session,
                f"❌ <b>[{escape_html(session.name)}]</b> tmux session not found",
                parse_mode='HTML'
            )
            return True

        send_message_session(session,
            f"📦 <b>[{escape_html(session.name)}]</b> Compacting context...",
            parse_mode='HTML'
        )
        if inject_to_tmux_session(session, '/compact'):
            log_session(session, "Compact command sent to Claude")
        else:
            send_message_session(session,
                f"❌ <b>[{escape_html(session.name)}]</b> Failed to send compact command",
                parse_mode='HTML'
            )
        return True

    # -------------------------------------------------------------------------
    # /preview - Terminal output preview
    # -------------------------------------------------------------------------
    elif cmd == '/preview':
        script = CLAUDE_HOME / 'hooks' / 'telegram-preview.sh'

        if not script.exists():
            send_message_session(session,
                f"❌ <b>[{escape_html(session.name)}]</b> Preview script not found",
                parse_mode='HTML'
            )
            return True

        if args.lower() == 'help':
            output = run_script_session(session, str(script), 'help')
            send_message_session(session,
                f"📺 <b>[{escape_html(session.name)}] Preview Help</b>\n\n"
                f"<pre>{escape_html(output[:3500])}</pre>",
                parse_mode='HTML'
            )
            return True

        send_message_session(session,
            f"📺 <b>[{escape_html(session.name)}]</b> Generating preview...",
            parse_mode='HTML'
        )
        output = run_script_session(session, str(script), args)

        if 'Error' in output or 'error' in output.lower():
            if message_id:
                set_message_reaction_session(session, message_id, "😱")
            send_message_session(session,
                f"⚠️ <b>[{escape_html(session.name)}]</b> {escape_html(output[:1000])}",
                parse_mode='HTML'
            )
        else:
            if message_id:
                set_message_reaction_session(session, message_id, "👀")

        return True

    # -------------------------------------------------------------------------
    # /notify - Notification control
    # -------------------------------------------------------------------------
    elif cmd == '/notify':
        script = CLAUDE_HOME / 'hooks' / 'remote-notify.sh'

        if not script.exists():
            send_message_session(session,
                f"❌ <b>[{escape_html(session.name)}]</b> Notify script not found",
                parse_mode='HTML'
            )
            return True

        valid_subcmds = ['on', 'off', 'status', 'config', 'start', 'stop', 'help']
        subcmd = args.split()[0].lower() if args else 'help'

        if subcmd not in valid_subcmds:
            send_message_session(session,
                f"❌ <b>[{escape_html(session.name)}]</b> Unknown subcommand: "
                f"<code>{escape_html(subcmd)}</code>\n\n"
                f"Valid: {', '.join(valid_subcmds)}\n"
                "Try: /notify help",
                parse_mode='HTML'
            )
            return True

        # Handle on/off - global notification flag
        if subcmd == 'on':
            notify_flag = CLAUDE_HOME / 'notifications-enabled'
            try:
                notify_flag.touch()
                log_session(session, f"Notifications enabled (flag: {notify_flag})")
                send_message_session(session,
                    f"🔔 <b>[{escape_html(session.name)}]</b> Notifications enabled (global)",
                    parse_mode='HTML'
                )
            except Exception as e:
                log_session(session, f"Failed to enable notifications: {e}", "ERROR")
                send_message_session(session,
                    f"❌ <b>[{escape_html(session.name)}]</b> Failed to enable notifications: "
                    f"{escape_html(str(e))}",
                    parse_mode='HTML'
                )
            return True

        if subcmd == 'off':
            notify_flag = CLAUDE_HOME / 'notifications-enabled'
            try:
                notify_flag.unlink(missing_ok=True)
                log_session(session, f"Notifications disabled (flag: {notify_flag})")
                send_message_session(session,
                    f"🔕 <b>[{escape_html(session.name)}]</b> Notifications disabled (global)",
                    parse_mode='HTML'
                )
            except Exception as e:
                log_session(session, f"Failed to disable notifications: {e}", "ERROR")
                send_message_session(session,
                    f"❌ <b>[{escape_html(session.name)}]</b> Failed to disable notifications: "
                    f"{escape_html(str(e))}",
                    parse_mode='HTML'
                )
            return True

        # Handle stop - pause THIS session only
        if subcmd == 'stop':
            session.paused = True
            log_session(session, "Stop command received - session paused")
            send_message_session(session,
                f"⏸️ <b>[{escape_html(session.name)}]</b> Session paused. "
                "Send /notify start to resume.",
                parse_mode='HTML'
            )
            return True

        # Handle start - resume THIS session
        if subcmd == 'start':
            if not session.paused:
                send_message_session(session,
                    f"✅ <b>[{escape_html(session.name)}]</b> Session already running",
                    parse_mode='HTML'
                )
            else:
                session.paused = False
                log_session(session, "Start command received - session resumed")
                send_message_session(session,
                    f"▶️ <b>[{escape_html(session.name)}]</b> Session resumed",
                    parse_mode='HTML'
                )
            return True

        output = run_script_session(session, str(script), subcmd)
        output = re.sub(r'\x1b\[[0-9;]*m', '', output)

        if subcmd == 'help':
            send_message_session(session,
                f"🔔 <b>[{escape_html(session.name)}] Notify Help</b>\n\n"
                f"<pre>{escape_html(output[:3500])}</pre>",
                parse_mode='HTML'
            )
        else:
            send_message_session(session,
                f"🔔 <b>[{escape_html(session.name)}] {escape_html(subcmd.title())}</b>\n\n"
                f"<pre>{escape_html(output[:2000])}</pre>",
                parse_mode='HTML'
            )

        return True

    # -------------------------------------------------------------------------
    # /output - Alias for /preview
    # -------------------------------------------------------------------------
    elif cmd == '/output':
        return handle_command_session(f'/preview {args}', from_user, message_id, session, manager)

    return False


def handle_media_message_session(message: dict, message_id: int, session: SessionState):
    """Handle incoming media message for a specific session.

    Returns tuple: (inject_text, success)
    """
    # Check for unsupported media types first
    for media_type, description in UNSUPPORTED_MEDIA_TYPES.items():
        if media_type in message:
            return (f"{description} not supported. Send photos or documents instead.", False)

    # Handle photos
    if 'photo' in message:
        photos = message['photo']
        if not photos:
            return ("Empty photo array", False)

        photo = photos[-1]
        file_id = photo.get('file_id')
        file_size = photo.get('file_size', 0)

        if file_size > MAX_FILE_SIZE:
            return (f"Photo too large ({file_size // 1024 // 1024}MB). Max: 20MB", False)

        return _download_and_format_session(file_id, 'photo', message, session)

    # Handle documents
    if 'document' in message:
        doc = message['document']
        file_id = doc.get('file_id')
        file_size = doc.get('file_size', 0)
        file_name = doc.get('file_name', 'document')

        if file_size > MAX_FILE_SIZE:
            return (f"Document too large ({file_size // 1024 // 1024}MB). Max: 20MB", False)

        return _download_and_format_session(file_id, 'document', message, session, file_name)

    return ("No media found in message", False)


def _download_and_format_session(file_id: str, media_type: str, message: dict,
                                 session: SessionState, original_filename: str = None):
    """Download media and format inject text for a session."""
    if not ensure_media_dir():
        return ("Failed to create media directory", False)

    file_info = get_telegram_file_session(file_id, session.bot_token)
    if not file_info:
        return ("Failed to get file info from Telegram", False)

    telegram_path = file_info.get('file_path')
    if not telegram_path:
        return ("No file_path in Telegram response", False)

    if original_filename:
        safe_name = sanitize_filename(original_filename)
    else:
        ext = Path(telegram_path).suffix or '.jpg'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = f"{media_type}_{timestamp}{ext}"

    local_filename = f"{session.name}-{safe_name}"
    local_path = MEDIA_TEMP_DIR / local_filename

    if not download_telegram_file_session(telegram_path, local_path, session.bot_token):
        return ("Failed to download file", False)

    caption = message.get('caption', '').strip()
    if media_type == 'photo':
        inject_text = f"[Image: {local_path}]"
    else:
        inject_text = f"[Document: {local_path}]"

    if caption:
        inject_text += f" {caption}"

    return (inject_text, True)


def get_telegram_file_session(file_id: str, bot_token: str) -> Optional[dict]:
    """Get file path from Telegram using file_id (session-aware)."""
    url = f"https://api.telegram.org/bot{bot_token}/getFile"
    params = {'file_id': file_id}

    try:
        response = requests.get(url, params=params, timeout=30)
        data = response.json()

        if data.get('ok'):
            return data.get('result', {})
        else:
            log_multi(f"getFile API error: {data.get('description', 'Unknown')}", "ERROR")
            return None
    except Exception as e:
        log_multi(f"Error getting file info: {e}", "ERROR")
        return None


def download_telegram_file_session(file_path: str, local_path: Path, bot_token: str) -> bool:
    """Download file from Telegram servers (session-aware)."""
    url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"

    try:
        response = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
        response.raise_for_status()

        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        log_multi(f"Downloaded: {local_path}")
        return True
    except requests.exceptions.Timeout:
        log_multi(f"Download timeout for {file_path}", "ERROR")
        return False
    except Exception as e:
        log_multi(f"Error downloading file: {e}", "ERROR")
        return False


# =============================================================================
# MULTI-SESSION MAIN LOOP
# =============================================================================

def run_multi_session():
    """Main loop for multi-session mode."""
    manager = SessionManager(CLAUDE_HOME)

    if not manager.scan_configs():
        log_multi("No valid sessions found", "ERROR")
        sys.exit(1)

    offset = None
    error_count = 0

    log_multi("Listening for messages (multi-session mode)...")

    while True:
        try:
            # Periodic config rescan (every 60s)
            if time.time() - manager.last_scan_time > CONFIG_RESCAN_INTERVAL:
                log_multi("Rescanning session configs...")
                manager.scan_configs()

            updates = get_updates_multi(offset, manager.bot_token)
            error_count = 0

            for update in updates:
                offset = update['update_id'] + 1

                # Handle callback_query (inline keyboard button clicks)
                callback_query = update.get('callback_query')
                if callback_query:
                    cb_id = callback_query.get('id')
                    cb_data = callback_query.get('data', '')
                    cb_message = callback_query.get('message', {})
                    cb_topic_id = str(cb_message.get('message_thread_id', ''))

                    log_multi(f"Callback: data={cb_data!r} topic={cb_topic_id!r}")

                    cb_session = manager.get_session_by_topic(cb_topic_id) if cb_topic_id else None

                    if not cb_session:
                        # No session found — answer callback to stop animation
                        log_multi(f"Callback: no session for topic {cb_topic_id!r} "
                                  f"(known: {list(manager.sessions.keys())})", "WARN")
                        # Answer using shared bot token to stop button animation
                        if manager.bot_token:
                            try:
                                requests.post(
                                    f"https://api.telegram.org/bot{manager.bot_token}/answerCallbackQuery",
                                    data={'callback_query_id': cb_id}, timeout=10)
                            except Exception:
                                pass
                        continue

                    if cb_data.startswith('opt:'):
                        parts = cb_data.split(':')
                        option_num = parts[-1] if len(parts) >= 3 else ''
                        from_chat = str(cb_message.get('chat', {}).get('id', ''))
                        cb_msg_id = cb_message.get('message_id')
                        cb_msg_text = cb_message.get('text', '')

                        if from_chat == cb_session.chat_id and option_num and not cb_session.paused:
                            # Find the label for the selected option from the keyboard
                            selected_label = option_num
                            reply_markup = cb_message.get('reply_markup', {})
                            for row in reply_markup.get('inline_keyboard', []):
                                for btn in row:
                                    if btn.get('callback_data', '') == cb_data:
                                        selected_label = btn.get('text', option_num)
                                        break

                            if inject_to_tmux_session(cb_session, option_num):
                                log_session(cb_session, f"Callback: injected option {option_num}")
                                answer_callback_query_session(cb_session, cb_id, f"Sent: {option_num}")
                                # Edit message to confirm selection and remove buttons
                                if cb_msg_id:
                                    confirm_button_selection(
                                        cb_session.bot_token, cb_session.chat_id,
                                        cb_msg_id, cb_msg_text, selected_label)
                            else:
                                log_session(cb_session, f"Callback: inject failed for option {option_num}", "WARN")
                                answer_callback_query_session(cb_session, cb_id, "Failed: session not found")
                        else:
                            reason = "paused" if cb_session.paused else "chat mismatch or empty option"
                            log_session(cb_session, f"Callback: skipped ({reason})", "WARN")
                            answer_callback_query_session(cb_session, cb_id,
                                "Session paused" if cb_session.paused else "")
                    else:
                        answer_callback_query_session(cb_session, cb_id)
                    continue

                message = update.get('message', {})

                # Get topic ID from message
                topic_id = str(message.get('message_thread_id', ''))
                if not topic_id:
                    # Ignore messages without topic ID in multi-session mode
                    continue

                # Route to session
                session = manager.get_session_by_topic(topic_id)
                if not session:
                    # Unknown topic - ignore
                    continue

                # Verify chat ID matches
                from_chat = str(message.get('chat', {}).get('id', ''))
                if from_chat != session.chat_id:
                    continue

                message_id = message.get('message_id')
                from_user = message.get('from', {}).get('username', 'unknown')
                text = message.get('text', '').strip()

                # When paused, only respond to /notify start
                if session.paused:
                    if text.lower() == '/notify start':
                        handle_command_session(text, from_user, message_id, session, manager)
                    continue

                # Check for media
                has_media = any(key in message for key in
                               ['photo', 'document', 'voice', 'video', 'video_note',
                                'audio', 'sticker', 'animation'])

                if has_media:
                    log_session(session, f"Received media from @{from_user}")
                    inject_text, success = handle_media_message_session(message, message_id, session)

                    if success:
                        if inject_to_tmux_session(session, inject_text):
                            set_message_reaction_session(session, message_id, "👀")
                        else:
                            set_message_reaction_session(session, message_id, "😱")
                            send_message_session(session,
                                f"❌ <b>[{escape_html(session.name)}]</b> Failed (session not found)",
                                parse_mode='HTML'
                            )
                    else:
                        set_message_reaction_session(session, message_id, "😱")
                        send_message_session(session,
                            f"❌ <b>[{escape_html(session.name)}]</b> {escape_html(inject_text)}",
                            parse_mode='HTML'
                        )
                    continue

                if not text:
                    continue

                log_session(session, f"Received from @{from_user}: {text[:50]}...")

                # Handle commands
                if text.startswith('/'):
                    if handle_command_session(text, from_user, message_id, session, manager):
                        continue

                # Inject into tmux
                if inject_to_tmux_session(session, text):
                    set_message_reaction_session(session, message_id, "👀")
                else:
                    set_message_reaction_session(session, message_id, "😱")
                    send_message_session(session,
                        f"❌ <b>[{escape_html(session.name)}]</b> Failed (session not found)",
                        parse_mode='HTML'
                    )

            if not updates:
                time.sleep(0.5)

        except KeyboardInterrupt:
            log_multi("Interrupted by user")
            return False
        except Exception as e:
            error_count += 1
            log_multi(f"Error in main loop: {e}", "ERROR")

            if error_count > 10:
                log_multi("Too many consecutive errors, triggering restart", "ERROR")
                return True

            wait_time = min(60, 2 ** error_count)
            log_multi(f"Waiting {wait_time}s before retry...", "WARN")
            time.sleep(wait_time)

    return False


def main_multi():
    """Entry point for multi-session mode."""
    log_multi("=" * 60)
    log_multi("Multi-Session Telegram Listener Starting")
    log_multi("=" * 60)

    # Write PID file for multi-session mode
    pid_file = CLAUDE_HOME / 'pids' / 'listener-multi.pid'
    try:
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
        log_multi(f"PID file: {pid_file}")
    except Exception as e:
        log_multi(f"Could not write PID file: {e}", "WARN")

    # Signal handlers
    def signal_handler(signum, frame):
        log_multi("Shutdown signal received")
        # Clean up all session media
        media_dir = Path('/tmp/claude-telegram')
        if media_dir.exists():
            try:
                for f in media_dir.glob('*'):
                    f.unlink()
            except Exception:
                pass
        # Remove PID file
        try:
            pid_file.unlink()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Main loop with restart logic
    restart_attempt = 0

    while restart_attempt < MAX_RESTART_ATTEMPTS:
        try:
            should_restart = run_multi_session()

            if not should_restart:
                break

            restart_attempt += 1
            delay = RESTART_DELAY_BASE * (2 ** (restart_attempt - 1))

            log_multi(f"Restarting in {delay}s (attempt {restart_attempt}/{MAX_RESTART_ATTEMPTS})...", "WARN")
            time.sleep(delay)
            log_multi("Restarting listener...", "INFO")

        except Exception as e:
            restart_attempt += 1
            log_multi(f"Fatal error: {e}", "ERROR")

            if restart_attempt >= MAX_RESTART_ATTEMPTS:
                break

            delay = RESTART_DELAY_BASE * (2 ** (restart_attempt - 1))
            time.sleep(delay)

    if restart_attempt >= MAX_RESTART_ATTEMPTS:
        log_multi(f"Giving up after {MAX_RESTART_ATTEMPTS} restart attempts", "ERROR")

    try:
        pid_file.unlink()
    except Exception:
        pass
    log_multi("Multi-session listener stopped")


def list_sessions():
    """List all configured sessions."""
    manager = SessionManager(CLAUDE_HOME)
    manager.scan_configs()

    if not manager.sessions:
        print("No sessions configured.")
        print(f"Add session configs to: {manager.sessions_dir}/")
        return

    print(f"Configured sessions ({len(manager.sessions)}):\n")
    for session in sorted(manager.sessions.values(), key=lambda s: s.name):
        print(f"  {session.name}")
        print(f"    Topic ID: {session.topic_id}")
        print(f"    tmux: {session.tmux_session}")
        print(f"    Config: {session.config_path}")
        print()


def notify_crash(attempt, max_attempts, error_msg):
    """Send notification about listener crash"""
    if attempt >= max_attempts:
        msg = (
            f"❌ <b>[{escape_html(SESSION_NAME)}]</b> Listener crashed after {max_attempts} attempts!\n\n"
            f"<b>Last error:</b>\n<pre>{escape_html(error_msg)}</pre>\n\n"
            "Restart manually with:\n/remote-notify start"
        )
    else:
        msg = (
            f"⚠️ <b>[{escape_html(SESSION_NAME)}]</b> Listener restarting "
            f"(attempt {attempt + 1}/{max_attempts})\n\n"
            f"<b>Error:</b>\n<pre>{escape_html(error_msg)}</pre>"
        )

    try:
        send_message(msg, parse_mode='HTML')
    except:
        pass  # Best effort

def run_listener():
    """Main listener loop - returns True if should restart, False if clean exit"""
    offset = None
    error_count = 0
    
    log("Listening for messages...")
    if TOPIC_ID:
        log(f"Filtering for topic {TOPIC_ID} only")
    
    while True:
        try:
            updates = get_updates(offset)
            error_count = 0
            
            for update in updates:
                offset = update['update_id'] + 1

                # Handle callback_query (inline keyboard button clicks)
                callback_query = update.get('callback_query')
                if callback_query:
                    cb_id = callback_query.get('id')
                    cb_data = callback_query.get('data', '')
                    cb_message = callback_query.get('message', {})

                    log(f"Callback: data={cb_data!r}")

                    if cb_data.startswith('opt:'):
                        parts = cb_data.split(':')
                        option_num = parts[-1] if len(parts) >= 3 else ''
                        from_chat = str(cb_message.get('chat', {}).get('id', ''))
                        cb_msg_id = cb_message.get('message_id')
                        cb_msg_text = cb_message.get('text', '')

                        if from_chat == str(CHAT_ID) and option_num:
                            # Find the label for the selected option from the keyboard
                            selected_label = option_num
                            reply_markup = cb_message.get('reply_markup', {})
                            for row in reply_markup.get('inline_keyboard', []):
                                for btn in row:
                                    if btn.get('callback_data', '') == cb_data:
                                        selected_label = btn.get('text', option_num)
                                        break

                            if inject_to_tmux(option_num):
                                log(f"Callback: injected option {option_num}")
                                answer_callback_query(cb_id, f"Sent: {option_num}")
                                # Edit message to confirm selection and remove buttons
                                if cb_msg_id:
                                    confirm_button_selection(
                                        BOT_TOKEN, str(CHAT_ID),
                                        cb_msg_id, cb_msg_text, selected_label)
                            else:
                                log(f"Callback: inject failed for option {option_num}", "WARN")
                                answer_callback_query(cb_id, "Failed: session not found")
                        else:
                            log(f"Callback: chat mismatch or empty option", "WARN")
                            answer_callback_query(cb_id)
                    else:
                        answer_callback_query(cb_id)
                    continue

                message = update.get('message', {})

                # Check if we should process this message
                if not should_process_message(message):
                    continue

                message_id = message.get('message_id')
                from_user = message.get('from', {}).get('username', 'unknown')
                text = message.get('text', '').strip()

                # When paused, only respond to /notify start
                if listener_paused:
                    if text.lower() == '/notify start':
                        handle_command(text, from_user, message_id)
                    # Silently ignore all other messages when paused
                    continue

                # Check for media first (photos, documents, unsupported types)
                has_media = any(key in message for key in
                               ['photo', 'document', 'voice', 'video', 'video_note',
                                'audio', 'sticker', 'animation'])

                if has_media:
                    log(f"Received media from @{from_user}")
                    inject_text, success = handle_media_message(message, message_id)

                    if success:
                        # Media processed successfully - inject to tmux
                        if inject_to_tmux(inject_text):
                            set_message_reaction(message_id, "👀")
                        else:
                            set_message_reaction(message_id, "😱")
                            send_message(
                                f"❌ <b>[{escape_html(SESSION_NAME)}]</b> Failed (session not found)",
                                parse_mode='HTML'
                            )
                    else:
                        # Media handling failed - send error message
                        set_message_reaction(message_id, "😱")
                        send_message(
                            f"❌ <b>[{escape_html(SESSION_NAME)}]</b> {escape_html(inject_text)}",
                            parse_mode='HTML'
                        )
                    continue

                # Handle text messages (text already extracted above for pause check)
                if not text:
                    continue

                log(f"Received from @{from_user}: {text[:50]}...")

                # Handle commands
                if text.startswith('/'):
                    if handle_command(text, from_user, message_id):
                        continue

                # Inject into tmux
                if inject_to_tmux(text):
                    set_message_reaction(message_id, "👀")
                else:
                    set_message_reaction(message_id, "😱")
                    send_message(
                        f"❌ <b>[{escape_html(SESSION_NAME)}]</b> Failed (session not found)",
                        parse_mode='HTML'
                    )
            
            if not updates:
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            log("Interrupted by user")
            return False  # Clean exit, don't restart
        except Exception as e:
            error_count += 1
            log(f"Error in main loop: {e}", "ERROR")
            
            if error_count > 10:
                log("Too many consecutive errors, triggering restart", "ERROR")
                return True  # Should restart
            
            wait_time = min(60, 2 ** error_count)
            log(f"Waiting {wait_time}s before retry...", "WARN")
            time.sleep(wait_time)
    
    return False

def main():
    log("=" * 60)
    log(f"Telegram Listener Starting")
    log(f"Session: {SESSION_NAME}")
    log("=" * 60)
    
    # Validate configuration
    if not BOT_TOKEN:
        log("TELEGRAM_BOT_TOKEN not configured", "ERROR")
        sys.exit(1)
    
    if not CHAT_ID:
        log("TELEGRAM_CHAT_ID not configured", "ERROR")
        sys.exit(1)
    
    log(f"Bot Token: {mask_sensitive(BOT_TOKEN, 5, 3)}")
    log(f"Chat ID: {mask_sensitive(CHAT_ID, 2, 2)}")
    log(f"Topic ID: {TOPIC_ID or '(none - processing all messages)'}")
    log(f"tmux Session: {TMUX_SESSION}")
    
    # Write PID file
    write_pid()
    log(f"PID file: {PID_FILE}")
    
    # Check tmux
    if not tmux_session_exists():
        log(f"tmux session '{TMUX_SESSION}' not found - waiting...", "WARN")
    else:
        log(f"tmux session '{TMUX_SESSION}' found")
    
    # Signal handlers
    def signal_handler(signum, frame):
        log("Shutdown signal received")
        cleanup_media_files()
        remove_pid()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Main loop with restart logic
    restart_attempt = 0
    
    while restart_attempt < MAX_RESTART_ATTEMPTS:
        try:
            should_restart = run_listener()
            
            if not should_restart:
                # Clean exit
                break
            
            # Crashed, try to restart
            restart_attempt += 1
            delay = RESTART_DELAY_BASE * (2 ** (restart_attempt - 1))
            
            log(f"Restarting in {delay}s (attempt {restart_attempt}/{MAX_RESTART_ATTEMPTS})...", "WARN")
            notify_crash(restart_attempt - 1, MAX_RESTART_ATTEMPTS, "Connection lost or repeated errors")
            
            time.sleep(delay)
            log("Restarting listener...", "INFO")
            
        except Exception as e:
            restart_attempt += 1
            log(f"Fatal error: {e}", "ERROR")
            notify_crash(restart_attempt - 1, MAX_RESTART_ATTEMPTS, str(e))
            
            if restart_attempt >= MAX_RESTART_ATTEMPTS:
                break
            
            delay = RESTART_DELAY_BASE * (2 ** (restart_attempt - 1))
            time.sleep(delay)
    
    if restart_attempt >= MAX_RESTART_ATTEMPTS:
        log(f"Giving up after {MAX_RESTART_ATTEMPTS} restart attempts", "ERROR")
        notify_crash(MAX_RESTART_ATTEMPTS, MAX_RESTART_ATTEMPTS, "Max restart attempts reached")
    
    remove_pid()
    log("Listener stopped")

if __name__ == '__main__':
    if args.list:
        list_sessions()
    elif MULTI_SESSION_MODE:
        main_multi()
    else:
        main()
