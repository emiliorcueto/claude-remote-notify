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
  /notify start|kill - Listener control
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
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' module not found")
    print("Install with: pip install --user requests")
    sys.exit(1)

# =============================================================================
# CONFIGURATION
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(description='Telegram listener for Claude sessions')
    parser.add_argument('--session', '-s', default=os.environ.get('CLAUDE_SESSION', 'default'),
                        help='Session name (default: "default" or CLAUDE_SESSION env)')
    return parser.parse_args()

args = parse_args()
SESSION_NAME = args.session

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
        'allowed_updates': ['message']
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

def handle_command(command, from_user):
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
            f"📊 [{SESSION_NAME}] Status\n\n"
            f"Session: {TMUX_SESSION}\n"
            f"Status: {session_status}"
            f"{topic_info}\n\n"
            f"Recent output:\n{snapshot[-800:]}"
        )
        return True
    
    # -------------------------------------------------------------------------
    # /ping - Connectivity test
    # -------------------------------------------------------------------------
    elif cmd == '/ping':
        send_message(f"🏓 [{SESSION_NAME}] Pong! Listener active.")
        return True
    
    # -------------------------------------------------------------------------
    # /help - Show all commands
    # -------------------------------------------------------------------------
    elif cmd == '/help':
        send_message(
            f"🤖 [{SESSION_NAME}] Telegram Commands\n\n"
            "━━━ Status ━━━\n"
            "/status - Session status + recent output\n"
            "/ping - Test listener connectivity\n"
            "/help - Show this help\n\n"
            "━━━ Context ━━━\n"
            "/clear - Clear Claude context\n"
            "/compact - Compact Claude context\n\n"
            "━━━ Preview ━━━\n"
            "/preview - Send last 50 lines (with colors)\n"
            "/preview N - Send last N lines\n"
            "/preview back N - Send Nth previous exchange\n"
            "/preview help - Show preview help\n"
            "/output - Alias for /preview\n\n"
            "━━━ Notifications ━━━\n"
            "/notify - Show notify help\n"
            "/notify on|off - Toggle notifications\n"
            "/notify status - Check notification state\n"
            "/notify config - Show full configuration\n"
            "/notify start|kill - Listener control\n\n"
            "━━━ Media ━━━\n"
            "📷 Photos - Downloaded, sent as [Image: /path]\n"
            "📄 Documents - Downloaded, sent as [Document: /path]\n"
            "❌ Voice/Video/Stickers - Not supported\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Any other text is sent directly to Claude."
        )
        return True

    # -------------------------------------------------------------------------
    # /clear - Clear Claude context
    # -------------------------------------------------------------------------
    elif cmd == '/clear':
        if not tmux_session_exists():
            send_message(f"❌ [{SESSION_NAME}] tmux session not found")
            return True

        send_message(f"🧹 [{SESSION_NAME}] Clearing context...")
        if inject_to_tmux('/clear'):
            log("Clear command sent to Claude")
        else:
            send_message(f"❌ [{SESSION_NAME}] Failed to send clear command")
        return True

    # -------------------------------------------------------------------------
    # /compact - Compact Claude context
    # -------------------------------------------------------------------------
    elif cmd == '/compact':
        if not tmux_session_exists():
            send_message(f"❌ [{SESSION_NAME}] tmux session not found")
            return True

        send_message(f"📦 [{SESSION_NAME}] Compacting context...")
        if inject_to_tmux('/compact'):
            log("Compact command sent to Claude")
        else:
            send_message(f"❌ [{SESSION_NAME}] Failed to send compact command")
        return True

    # -------------------------------------------------------------------------
    # /preview - Terminal output preview (runs telegram-preview.sh)
    # -------------------------------------------------------------------------
    elif cmd == '/preview':
        script = CLAUDE_HOME / 'hooks' / 'telegram-preview.sh'
        
        if not script.exists():
            send_message(f"❌ [{SESSION_NAME}] Preview script not found")
            return True
        
        # Handle /preview help specially - capture and send as message
        if args.lower() == 'help':
            output = run_script(str(script), 'help')
            send_message(f"📺 [{SESSION_NAME}] Preview Help\n\n{output[:3500]}")
            return True
        
        # For actual preview, the script sends the file directly to Telegram
        send_message(f"📺 [{SESSION_NAME}] Generating preview...")
        output = run_script(str(script), args)
        
        # If there was an error (script outputs to stderr), report it
        if 'Error' in output or 'error' in output.lower():
            send_message(f"⚠️ [{SESSION_NAME}] {output[:1000]}")
        
        return True
    
    # -------------------------------------------------------------------------
    # /notify - Notification control (runs remote-notify.sh)
    # -------------------------------------------------------------------------
    elif cmd == '/notify':
        script = CLAUDE_HOME / 'hooks' / 'remote-notify.sh'

        if not script.exists():
            send_message(f"❌ [{SESSION_NAME}] Notify script not found")
            return True

        # Valid subcommands
        valid_subcmds = ['on', 'off', 'status', 'config', 'start', 'kill', 'help']
        subcmd = args.split()[0].lower() if args else 'help'

        if subcmd not in valid_subcmds:
            send_message(
                f"❌ [{SESSION_NAME}] Unknown subcommand: {subcmd}\n\n"
                f"Valid: {', '.join(valid_subcmds)}\n"
                "Try: /notify help"
            )
            return True

        # For on/off, handle flag file directly to avoid subprocess env issues
        if subcmd == 'on':
            notify_flag = CLAUDE_HOME / 'notifications-enabled'
            try:
                notify_flag.touch()
                log(f"Notifications enabled (flag: {notify_flag})")
                send_message(f"🔔 [{SESSION_NAME}] Notifications enabled")
            except Exception as e:
                log(f"Failed to enable notifications: {e}", "ERROR")
                send_message(f"❌ [{SESSION_NAME}] Failed to enable notifications: {e}")
            return True

        if subcmd == 'off':
            notify_flag = CLAUDE_HOME / 'notifications-enabled'
            try:
                notify_flag.unlink(missing_ok=True)
                log(f"Notifications disabled (flag: {notify_flag})")
                send_message(f"🔕 [{SESSION_NAME}] Notifications disabled")
            except Exception as e:
                log(f"Failed to disable notifications: {e}", "ERROR")
                send_message(f"❌ [{SESSION_NAME}] Failed to disable notifications: {e}")
            return True

        # Handle kill directly - send confirmation before exiting
        if subcmd == 'kill':
            log("Kill command received - shutting down gracefully")
            send_message(f"🛑 [{SESSION_NAME}] Listener shutting down")
            cleanup_media_files()
            remove_pid()
            sys.exit(0)

        output = run_script(str(script), subcmd)

        # Clean up ANSI color codes for Telegram
        output = re.sub(r'\x1b\[[0-9;]*m', '', output)

        # Format response based on subcommand
        if subcmd == 'help':
            send_message(f"🔔 [{SESSION_NAME}] Notify Help\n\n{output[:3500]}")
        else:
            send_message(f"🔔 [{SESSION_NAME}] {subcmd.title()}\n\n{output[:2000]}")

        return True
    
    # -------------------------------------------------------------------------
    # /output - Alias for /preview
    # -------------------------------------------------------------------------
    elif cmd == '/output':
        # Redirect to /preview handler
        return handle_command(f'/preview {args}', from_user)
    
    return False

# =============================================================================
# MAIN LOOP
# =============================================================================

MAX_RESTART_ATTEMPTS = 3
RESTART_DELAY_BASE = 5  # seconds

def notify_crash(attempt, max_attempts, error_msg):
    """Send notification about listener crash"""
    if attempt >= max_attempts:
        msg = f"❌ [{SESSION_NAME}] Listener crashed after {max_attempts} attempts!\n\nLast error: {error_msg}\n\nRestart manually with:\n/remote-notify start"
    else:
        msg = f"⚠️ [{SESSION_NAME}] Listener restarting (attempt {attempt + 1}/{max_attempts})\n\nError: {error_msg}"
    
    try:
        send_message(msg)
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
                
                message = update.get('message', {})
                
                # Check if we should process this message
                if not should_process_message(message):
                    continue

                message_id = message.get('message_id')
                from_user = message.get('from', {}).get('username', 'unknown')

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
                            send_message(f"❌ [{SESSION_NAME}] Failed (session not found)")
                    else:
                        # Media handling failed - send error message
                        set_message_reaction(message_id, "😱")
                        send_message(f"❌ [{SESSION_NAME}] {inject_text}")
                    continue

                # Handle text messages
                text = message.get('text', '').strip()

                if not text:
                    continue

                log(f"Received from @{from_user}: {text[:50]}...")

                # Handle commands
                if text.startswith('/'):
                    if handle_command(text, from_user):
                        continue

                # Inject into tmux
                if inject_to_tmux(text):
                    # React with 👀 to acknowledge receipt (no noisy "Sent" message)
                    # Note: Telegram only allows specific emojis as reactions
                    set_message_reaction(message_id, "👀")
                else:
                    # Failure: react with 😱 and send error message
                    set_message_reaction(message_id, "😱")
                    send_message(f"❌ [{SESSION_NAME}] Failed (session not found)")
            
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
    main()
