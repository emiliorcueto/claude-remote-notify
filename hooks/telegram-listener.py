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
  /preview [N]       - Send terminal output (default 50 lines)
  /preview back N    - Send Nth previous exchange
  /preview help      - Preview help
  /notify on|off     - Toggle notifications
  /notify status     - Notification state
  /notify config     - Full configuration
  /notify start|kill - Listener control
  /notify help       - Notify help
  (any text)         - Sent to Claude

=============================================================================
"""

import os
import sys
import time
import subprocess
import signal
import argparse
import re
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
# TMUX INTERACTION
# =============================================================================

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
    """
    if not tmux_session_exists():
        log(f"tmux session '{TMUX_SESSION}' not found", "WARN")
        return False

    try:
        # Send text literally (handles multi-line, special chars)
        # The '--' prevents text starting with '-' from being parsed as options
        subprocess.run(
            ['tmux', 'send-keys', '-t', TMUX_SESSION, '-l', '--', text],
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
    """Run a hook script and return output"""
    try:
        cmd = f"{script_path} {args}".strip()
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            env={
                **os.environ,
                'CLAUDE_SESSION': SESSION_NAME,
                'TMUX_SESSION': TMUX_SESSION,
                'CLAUDE_HOME': str(CLAUDE_HOME)
            }
        )
        output = result.stdout + result.stderr
        return output.strip() if output.strip() else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Script timed out after 60 seconds"
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
            "━━━━━━━━━━━━━━━━━━\n"
            "Any other text is sent directly to Claude."
        )
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
        
        output = run_script(str(script), subcmd)
        
        # Clean up ANSI color codes for Telegram
        output = re.sub(r'\x1b\[[0-9;]*m', '', output)
        
        # Format response based on subcommand
        if subcmd == 'help':
            send_message(f"🔔 [{SESSION_NAME}] Notify Help\n\n{output[:3500]}")
        elif subcmd in ['on', 'off']:
            # These already send their own Telegram messages, just log
            log(f"Notify {subcmd}: {output}")
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
                
                text = message.get('text', '').strip()
                message_id = message.get('message_id')
                from_user = message.get('from', {}).get('username', 'unknown')

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
    
    log(f"Bot Token: {BOT_TOKEN[:10]}...{BOT_TOKEN[-5:]}")
    log(f"Chat ID: {CHAT_ID}")
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
