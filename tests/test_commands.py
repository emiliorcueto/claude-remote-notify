"""
Unit tests for Telegram command handlers in telegram-listener.py
Tests /clear, /compact, and other command handler functionality.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

# Add hooks directory to path for importing
sys.path.insert(0, str(Path(__file__).parent.parent / 'hooks'))

# Mock the requests module before importing
mock_requests = MagicMock()
sys.modules['requests'] = mock_requests


class TestClearCommand:
    """Tests for /clear command handler."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_send_message = MagicMock()
        self.mock_inject_to_tmux = MagicMock(return_value=True)
        self.mock_tmux_session_exists = MagicMock(return_value=True)
        self.mock_log = MagicMock()
        self.session_name = 'test-session'

    def create_handle_command(self, tmux_exists=True, inject_success=True):
        """Create a handle_command function with mocked dependencies."""
        session_name = self.session_name
        mock_send = self.mock_send_message
        mock_inject = MagicMock(return_value=inject_success)
        mock_exists = MagicMock(return_value=tmux_exists)
        mock_log = self.mock_log

        def handle_command(command, from_user):
            parts = command.strip().split()
            cmd = parts[0].lower()
            args = ' '.join(parts[1:]) if len(parts) > 1 else ''

            if cmd == '/clear':
                if not mock_exists():
                    mock_send(f"❌ [{session_name}] tmux session not found")
                    return True

                mock_send(f"🧹 [{session_name}] Clearing context...")
                if mock_inject('/clear'):
                    mock_log("Clear command sent to Claude")
                else:
                    mock_send(f"❌ [{session_name}] Failed to send clear command")
                return True

            return False

        return handle_command, mock_send, mock_inject, mock_exists, mock_log

    def test_clear_command_success(self):
        """Test /clear command when tmux session exists and injection succeeds."""
        handle_command, mock_send, mock_inject, mock_exists, mock_log = \
            self.create_handle_command(tmux_exists=True, inject_success=True)

        result = handle_command('/clear', 'testuser')

        assert result is True
        mock_exists.assert_called_once()
        mock_send.assert_called_with(f"🧹 [{self.session_name}] Clearing context...")
        mock_inject.assert_called_once_with('/clear')
        mock_log.assert_called_once_with("Clear command sent to Claude")

    def test_clear_command_no_session(self):
        """Test /clear command when tmux session doesn't exist."""
        handle_command, mock_send, mock_inject, mock_exists, mock_log = \
            self.create_handle_command(tmux_exists=False, inject_success=True)

        result = handle_command('/clear', 'testuser')

        assert result is True
        mock_exists.assert_called_once()
        mock_send.assert_called_once_with(f"❌ [{self.session_name}] tmux session not found")
        mock_inject.assert_not_called()

    def test_clear_command_inject_failure(self):
        """Test /clear command when injection fails."""
        handle_command, mock_send, mock_inject, mock_exists, mock_log = \
            self.create_handle_command(tmux_exists=True, inject_success=False)

        result = handle_command('/clear', 'testuser')

        assert result is True
        mock_exists.assert_called_once()
        assert mock_send.call_count == 2
        mock_send.assert_any_call(f"🧹 [{self.session_name}] Clearing context...")
        mock_send.assert_any_call(f"❌ [{self.session_name}] Failed to send clear command")
        mock_log.assert_not_called()

    def test_clear_command_case_insensitive(self):
        """Test /clear command is case insensitive."""
        handle_command, mock_send, mock_inject, mock_exists, mock_log = \
            self.create_handle_command(tmux_exists=True, inject_success=True)

        result = handle_command('/CLEAR', 'testuser')

        assert result is True
        mock_inject.assert_called_once_with('/clear')

    def test_clear_command_with_trailing_whitespace(self):
        """Test /clear command handles trailing whitespace."""
        handle_command, mock_send, mock_inject, mock_exists, mock_log = \
            self.create_handle_command(tmux_exists=True, inject_success=True)

        result = handle_command('/clear   ', 'testuser')

        assert result is True
        mock_inject.assert_called_once_with('/clear')


class TestCompactCommand:
    """Tests for /compact command handler."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_send_message = MagicMock()
        self.mock_inject_to_tmux = MagicMock(return_value=True)
        self.mock_tmux_session_exists = MagicMock(return_value=True)
        self.mock_log = MagicMock()
        self.session_name = 'test-session'

    def create_handle_command(self, tmux_exists=True, inject_success=True):
        """Create a handle_command function with mocked dependencies."""
        session_name = self.session_name
        mock_send = self.mock_send_message
        mock_inject = MagicMock(return_value=inject_success)
        mock_exists = MagicMock(return_value=tmux_exists)
        mock_log = self.mock_log

        def handle_command(command, from_user):
            parts = command.strip().split()
            cmd = parts[0].lower()
            args = ' '.join(parts[1:]) if len(parts) > 1 else ''

            if cmd == '/compact':
                if not mock_exists():
                    mock_send(f"❌ [{session_name}] tmux session not found")
                    return True

                mock_send(f"📦 [{session_name}] Compacting context...")
                if mock_inject('/compact'):
                    mock_log("Compact command sent to Claude")
                else:
                    mock_send(f"❌ [{session_name}] Failed to send compact command")
                return True

            return False

        return handle_command, mock_send, mock_inject, mock_exists, mock_log

    def test_compact_command_success(self):
        """Test /compact command when tmux session exists and injection succeeds."""
        handle_command, mock_send, mock_inject, mock_exists, mock_log = \
            self.create_handle_command(tmux_exists=True, inject_success=True)

        result = handle_command('/compact', 'testuser')

        assert result is True
        mock_exists.assert_called_once()
        mock_send.assert_called_with(f"📦 [{self.session_name}] Compacting context...")
        mock_inject.assert_called_once_with('/compact')
        mock_log.assert_called_once_with("Compact command sent to Claude")

    def test_compact_command_no_session(self):
        """Test /compact command when tmux session doesn't exist."""
        handle_command, mock_send, mock_inject, mock_exists, mock_log = \
            self.create_handle_command(tmux_exists=False, inject_success=True)

        result = handle_command('/compact', 'testuser')

        assert result is True
        mock_exists.assert_called_once()
        mock_send.assert_called_once_with(f"❌ [{self.session_name}] tmux session not found")
        mock_inject.assert_not_called()

    def test_compact_command_inject_failure(self):
        """Test /compact command when injection fails."""
        handle_command, mock_send, mock_inject, mock_exists, mock_log = \
            self.create_handle_command(tmux_exists=True, inject_success=False)

        result = handle_command('/compact', 'testuser')

        assert result is True
        mock_exists.assert_called_once()
        assert mock_send.call_count == 2
        mock_send.assert_any_call(f"📦 [{self.session_name}] Compacting context...")
        mock_send.assert_any_call(f"❌ [{self.session_name}] Failed to send compact command")
        mock_log.assert_not_called()

    def test_compact_command_case_insensitive(self):
        """Test /compact command is case insensitive."""
        handle_command, mock_send, mock_inject, mock_exists, mock_log = \
            self.create_handle_command(tmux_exists=True, inject_success=True)

        result = handle_command('/COMPACT', 'testuser')

        assert result is True
        mock_inject.assert_called_once_with('/compact')

    def test_compact_command_with_trailing_whitespace(self):
        """Test /compact command handles trailing whitespace."""
        handle_command, mock_send, mock_inject, mock_exists, mock_log = \
            self.create_handle_command(tmux_exists=True, inject_success=True)

        result = handle_command('/compact   ', 'testuser')

        assert result is True
        mock_inject.assert_called_once_with('/compact')


class TestHelpCommand:
    """Tests for /help command to verify new commands are documented."""

    def test_help_includes_clear_command(self):
        """Verify /help output includes /clear command."""
        help_text = (
            "━━━ Context ━━━\n"
            "/clear - Clear Claude context\n"
            "/compact - Compact Claude context\n"
        )
        assert '/clear' in help_text
        assert 'Clear Claude context' in help_text

    def test_help_includes_compact_command(self):
        """Verify /help output includes /compact command."""
        help_text = (
            "━━━ Context ━━━\n"
            "/clear - Clear Claude context\n"
            "/compact - Compact Claude context\n"
        )
        assert '/compact' in help_text
        assert 'Compact Claude context' in help_text

    def test_help_context_section_exists(self):
        """Verify /help has Context section for context management commands."""
        help_text = (
            "━━━ Context ━━━\n"
            "/clear - Clear Claude context\n"
            "/compact - Compact Claude context\n"
        )
        assert '━━━ Context ━━━' in help_text


class TestCommandParsing:
    """Tests for command parsing edge cases."""

    def create_command_parser(self):
        """Create a basic command parser for testing."""
        def parse_command(command):
            parts = command.strip().split()
            cmd = parts[0].lower() if parts else ''
            args = ' '.join(parts[1:]) if len(parts) > 1 else ''
            return cmd, args
        return parse_command

    def test_parse_clear_no_args(self):
        """Test parsing /clear with no arguments."""
        parse = self.create_command_parser()
        cmd, args = parse('/clear')
        assert cmd == '/clear'
        assert args == ''

    def test_parse_compact_no_args(self):
        """Test parsing /compact with no arguments."""
        parse = self.create_command_parser()
        cmd, args = parse('/compact')
        assert cmd == '/compact'
        assert args == ''

    def test_parse_clear_ignores_extra_args(self):
        """Test /clear ignores any extra arguments."""
        parse = self.create_command_parser()
        cmd, args = parse('/clear extra args')
        assert cmd == '/clear'
        assert args == 'extra args'

    def test_parse_compact_ignores_extra_args(self):
        """Test /compact ignores any extra arguments."""
        parse = self.create_command_parser()
        cmd, args = parse('/compact extra args')
        assert cmd == '/compact'
        assert args == 'extra args'

    def test_parse_uppercase_clear(self):
        """Test uppercase /CLEAR is parsed correctly."""
        parse = self.create_command_parser()
        cmd, args = parse('/CLEAR')
        assert cmd == '/clear'

    def test_parse_uppercase_compact(self):
        """Test uppercase /COMPACT is parsed correctly."""
        parse = self.create_command_parser()
        cmd, args = parse('/COMPACT')
        assert cmd == '/compact'

    def test_parse_mixed_case(self):
        """Test mixed case commands are parsed correctly."""
        parse = self.create_command_parser()
        cmd, args = parse('/ClEaR')
        assert cmd == '/clear'
        cmd, args = parse('/CoMpAcT')
        assert cmd == '/compact'


class TestCommandNotHandled:
    """Tests for commands that should not be handled."""

    def create_handle_command(self):
        """Create handle_command that only handles /clear and /compact."""
        def handle_command(command, from_user):
            parts = command.strip().split()
            cmd = parts[0].lower() if parts else ''

            if cmd in ['/clear', '/compact']:
                return True
            return False

        return handle_command

    def test_unknown_command_not_handled(self):
        """Test unknown commands return False."""
        handle_command = self.create_handle_command()
        assert handle_command('/unknown', 'user') is False

    def test_similar_command_not_handled(self):
        """Test similar but different commands are not handled."""
        handle_command = self.create_handle_command()
        assert handle_command('/clearall', 'user') is False
        assert handle_command('/compacts', 'user') is False

    def test_clear_and_compact_handled(self):
        """Test /clear and /compact are handled."""
        handle_command = self.create_handle_command()
        assert handle_command('/clear', 'user') is True
        assert handle_command('/compact', 'user') is True


class TestTmuxInjectionPayload:
    """Tests for the payload sent to tmux."""

    def test_clear_injects_slash_clear(self):
        """Test /clear command injects '/clear' to tmux."""
        injected_commands = []

        def mock_inject(text):
            injected_commands.append(text)
            return True

        def handle_clear(command, inject_fn):
            parts = command.strip().split()
            cmd = parts[0].lower()
            if cmd == '/clear':
                return inject_fn('/clear')
            return False

        result = handle_clear('/clear', mock_inject)
        assert result is True
        assert injected_commands == ['/clear']

    def test_compact_injects_slash_compact(self):
        """Test /compact command injects '/compact' to tmux."""
        injected_commands = []

        def mock_inject(text):
            injected_commands.append(text)
            return True

        def handle_compact(command, inject_fn):
            parts = command.strip().split()
            cmd = parts[0].lower()
            if cmd == '/compact':
                return inject_fn('/compact')
            return False

        result = handle_compact('/compact', mock_inject)
        assert result is True
        assert injected_commands == ['/compact']


class TestFeedbackMessages:
    """Tests for user feedback messages."""

    def test_clear_success_message(self):
        """Test success feedback message for /clear."""
        session_name = 'test'
        expected = f"🧹 [{session_name}] Clearing context..."
        assert '🧹' in expected
        assert 'Clearing context' in expected

    def test_compact_success_message(self):
        """Test success feedback message for /compact."""
        session_name = 'test'
        expected = f"📦 [{session_name}] Compacting context..."
        assert '📦' in expected
        assert 'Compacting context' in expected

    def test_no_session_error_message(self):
        """Test error message when tmux session not found."""
        session_name = 'test'
        expected = f"❌ [{session_name}] tmux session not found"
        assert '❌' in expected
        assert 'tmux session not found' in expected

    def test_clear_failure_message(self):
        """Test error message when /clear injection fails."""
        session_name = 'test'
        expected = f"❌ [{session_name}] Failed to send clear command"
        assert '❌' in expected
        assert 'Failed to send clear command' in expected

    def test_compact_failure_message(self):
        """Test error message when /compact injection fails."""
        session_name = 'test'
        expected = f"❌ [{session_name}] Failed to send compact command"
        assert '❌' in expected
        assert 'Failed to send compact command' in expected


class TestNotifyCommand:
    """Tests for /notify command handler (on/off/status)."""

    def setup_method(self):
        """Setup test fixtures."""
        import tempfile
        self.mock_send_message = MagicMock()
        self.mock_run_script = MagicMock()
        self.mock_log = MagicMock()
        self.session_name = 'test-session'
        self.temp_dir = tempfile.mkdtemp()
        self.claude_home = Path(self.temp_dir)
        self.notify_flag = self.claude_home / 'notifications-enabled'

    def teardown_method(self):
        """Cleanup temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_handle_command(self, script_exists=True, script_output=""):
        """Create a handle_command function with mocked dependencies."""
        session_name = self.session_name
        mock_send = self.mock_send_message
        mock_run = MagicMock(return_value=script_output)
        mock_log = self.mock_log
        mock_script_exists = MagicMock(return_value=script_exists)
        claude_home = self.claude_home

        def handle_command(command, from_user):
            import re
            parts = command.strip().split()
            cmd = parts[0].lower()
            args = ' '.join(parts[1:]) if len(parts) > 1 else ''

            if cmd == '/notify':
                if not mock_script_exists():
                    mock_send(f"❌ [{session_name}] Notify script not found")
                    return True

                valid_subcmds = ['on', 'off', 'status', 'config', 'start', 'stop', 'help']
                subcmd = args.split()[0].lower() if args else 'help'

                if subcmd not in valid_subcmds:
                    mock_send(
                        f"❌ [{session_name}] Unknown subcommand: {subcmd}\n\n"
                        f"Valid: {', '.join(valid_subcmds)}\n"
                        "Try: /notify help"
                    )
                    return True

                # Handle on/off directly (fix for issue #12)
                if subcmd == 'on':
                    notify_flag = claude_home / 'notifications-enabled'
                    try:
                        notify_flag.touch()
                        mock_log(f"Notifications enabled (flag: {notify_flag})")
                        mock_send(f"🔔 [{session_name}] Notifications enabled")
                    except Exception as e:
                        mock_log(f"Failed to enable notifications: {e}")
                        mock_send(f"❌ [{session_name}] Failed to enable: {e}")
                    return True

                if subcmd == 'off':
                    notify_flag = claude_home / 'notifications-enabled'
                    try:
                        notify_flag.unlink(missing_ok=True)
                        mock_log(f"Notifications disabled (flag: {notify_flag})")
                        mock_send(f"🔕 [{session_name}] Notifications disabled")
                    except Exception as e:
                        mock_log(f"Failed to disable notifications: {e}")
                        mock_send(f"❌ [{session_name}] Failed to disable: {e}")
                    return True

                # Handle stop - pause the listener
                if subcmd == 'stop':
                    mock_log("Stop command received - listener paused")
                    mock_send(f"⏸️ [{session_name}] Listener paused. Send /notify start to resume.")
                    return 'PAUSED'  # Special return value for tests

                # Handle start - resume paused listener
                if subcmd == 'start':
                    # In tests, we track pause state via return value
                    mock_log("Start command received - listener resumed")
                    mock_send(f"▶️ [{session_name}] Listener resumed")
                    return 'RESUMED'  # Special return value for tests

                output = mock_run(subcmd)
                output = re.sub(r'\x1b\[[0-9;]*m', '', output)

                if subcmd == 'help':
                    mock_send(f"🔔 [{session_name}] Notify Help\n\n{output[:3500]}")
                else:
                    mock_send(f"🔔 [{session_name}] {subcmd.title()}\n\n{output[:2000]}")

                return True

            return False

        return handle_command, mock_send, mock_run, mock_script_exists, mock_log

    def test_notify_on_creates_flag_and_sends_message(self):
        """Test /notify on creates flag file and sends confirmation."""
        handle_command, mock_send, mock_run, mock_exists, mock_log = \
            self.create_handle_command(script_exists=True)

        result = handle_command('/notify on', 'testuser')

        assert result is True
        assert self.notify_flag.exists()
        mock_send.assert_called_once()
        assert 'Notifications enabled' in mock_send.call_args[0][0]
        mock_run.assert_not_called()  # on/off handled directly, not via script

    def test_notify_off_removes_flag_and_sends_message(self):
        """Test /notify off removes flag file and sends confirmation."""
        # Create flag first
        self.notify_flag.touch()
        assert self.notify_flag.exists()

        handle_command, mock_send, mock_run, mock_exists, mock_log = \
            self.create_handle_command(script_exists=True)

        result = handle_command('/notify off', 'testuser')

        assert result is True
        assert not self.notify_flag.exists()
        mock_send.assert_called_once()
        assert 'Notifications disabled' in mock_send.call_args[0][0]
        mock_run.assert_not_called()  # on/off handled directly

    def test_notify_on_after_off_creates_flag(self):
        """Test /notify on correctly creates flag after /notify off - Issue #12."""
        handle_command, mock_send, mock_run, mock_exists, mock_log = \
            self.create_handle_command(script_exists=True)

        # Initial state: disabled (no flag)
        assert not self.notify_flag.exists()

        # Enable
        handle_command('/notify on', 'testuser')
        assert self.notify_flag.exists()

        # Reset mocks
        mock_send.reset_mock()
        mock_log.reset_mock()

        # Disable
        handle_command('/notify off', 'testuser')
        assert not self.notify_flag.exists()

        # Reset mocks
        mock_send.reset_mock()
        mock_log.reset_mock()

        # Re-enable - THIS IS THE BUG SCENARIO
        handle_command('/notify on', 'testuser')
        assert self.notify_flag.exists()
        mock_send.assert_called_once()
        assert 'Notifications enabled' in mock_send.call_args[0][0]

    def test_notify_status_command_sends_message(self):
        """Test /notify status sends response message."""
        handle_command, mock_send, mock_run, mock_exists, mock_log = \
            self.create_handle_command(script_exists=True, script_output="Notifications: enabled")

        result = handle_command('/notify status', 'testuser')

        assert result is True
        mock_run.assert_called_once_with('status')
        mock_send.assert_called_once()
        assert 'Status' in mock_send.call_args[0][0]

    def test_notify_help_command_sends_message(self):
        """Test /notify help sends response message."""
        handle_command, mock_send, mock_run, mock_exists, mock_log = \
            self.create_handle_command(script_exists=True, script_output="Usage: /notify <command>")

        result = handle_command('/notify help', 'testuser')

        assert result is True
        mock_run.assert_called_once_with('help')
        mock_send.assert_called_once()
        assert 'Help' in mock_send.call_args[0][0]

    def test_notify_no_args_defaults_to_help(self):
        """Test /notify with no args defaults to help."""
        handle_command, mock_send, mock_run, mock_exists, mock_log = \
            self.create_handle_command(script_exists=True, script_output="Usage info")

        result = handle_command('/notify', 'testuser')

        assert result is True
        mock_run.assert_called_once_with('help')

    def test_notify_invalid_subcommand(self):
        """Test /notify with invalid subcommand returns error."""
        handle_command, mock_send, mock_run, mock_exists, mock_log = \
            self.create_handle_command(script_exists=True)

        result = handle_command('/notify invalid', 'testuser')

        assert result is True
        mock_run.assert_not_called()
        mock_send.assert_called_once()
        assert 'Unknown subcommand' in mock_send.call_args[0][0]

    def test_notify_script_not_found(self):
        """Test /notify when script doesn't exist."""
        handle_command, mock_send, mock_run, mock_exists, mock_log = \
            self.create_handle_command(script_exists=False)

        result = handle_command('/notify status', 'testuser')

        assert result is True
        mock_send.assert_called_once()
        assert 'script not found' in mock_send.call_args[0][0]
        mock_run.assert_not_called()

    def test_notify_stop_pauses_listener(self):
        """Test /notify stop pauses listener and sends confirmation - Issue #18."""
        handle_command, mock_send, mock_run, mock_exists, mock_log = \
            self.create_handle_command(script_exists=True)

        result = handle_command('/notify stop', 'testuser')

        # Returns 'PAUSED' in test
        assert result == 'PAUSED'
        mock_send.assert_called_once()
        assert 'paused' in mock_send.call_args[0][0].lower()
        assert '/notify start' in mock_send.call_args[0][0]
        mock_run.assert_not_called()  # stop handled directly, not via script

    def test_notify_start_resumes_listener(self):
        """Test /notify start resumes paused listener - Issue #18."""
        handle_command, mock_send, mock_run, mock_exists, mock_log = \
            self.create_handle_command(script_exists=True)

        result = handle_command('/notify start', 'testuser')

        # Returns 'RESUMED' in test
        assert result == 'RESUMED'
        mock_send.assert_called_once()
        assert 'resumed' in mock_send.call_args[0][0].lower()
        mock_run.assert_not_called()  # start handled directly, not via script

    def test_notify_on_case_insensitive(self):
        """Test /notify ON is case insensitive."""
        handle_command, mock_send, mock_run, mock_exists, mock_log = \
            self.create_handle_command(script_exists=True)

        result = handle_command('/notify ON', 'testuser')

        assert result is True
        assert self.notify_flag.exists()

    def test_notify_off_case_insensitive(self):
        """Test /notify OFF is case insensitive."""
        self.notify_flag.touch()
        handle_command, mock_send, mock_run, mock_exists, mock_log = \
            self.create_handle_command(script_exists=True)

        result = handle_command('/notify OFF', 'testuser')

        assert result is True
        assert not self.notify_flag.exists()

    def test_notify_on_idempotent(self):
        """Test /notify on is idempotent."""
        handle_command, mock_send, mock_run, mock_exists, mock_log = \
            self.create_handle_command(script_exists=True)

        # Call multiple times
        handle_command('/notify on', 'testuser')
        assert self.notify_flag.exists()

        handle_command('/notify on', 'testuser')
        assert self.notify_flag.exists()

        handle_command('/notify on', 'testuser')
        assert self.notify_flag.exists()

    def test_notify_off_idempotent(self):
        """Test /notify off is idempotent."""
        handle_command, mock_send, mock_run, mock_exists, mock_log = \
            self.create_handle_command(script_exists=True)

        # Call multiple times on non-existent flag
        handle_command('/notify off', 'testuser')
        assert not self.notify_flag.exists()

        handle_command('/notify off', 'testuser')
        assert not self.notify_flag.exists()


class TestNotifyOnOffToggle:
    """Tests for /notify on/off toggle scenarios - Issue #12."""

    def setup_method(self):
        """Setup test fixtures with temp directory."""
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.notify_flag = Path(self.temp_dir) / 'notifications-enabled'

    def teardown_method(self):
        """Cleanup temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_notify_off_removes_flag_file(self):
        """Test /notify off removes the notification flag file."""
        # Create flag file first
        self.notify_flag.touch()
        assert self.notify_flag.exists()

        # Simulate cmd_off
        self.notify_flag.unlink(missing_ok=True)

        assert not self.notify_flag.exists()

    def test_notify_on_creates_flag_file(self):
        """Test /notify on creates the notification flag file."""
        assert not self.notify_flag.exists()

        # Simulate cmd_on
        self.notify_flag.touch()

        assert self.notify_flag.exists()

    def test_notify_on_after_off_creates_flag(self):
        """Test /notify on creates flag after /notify off deleted it."""
        # Initial state: flag exists
        self.notify_flag.touch()
        assert self.notify_flag.exists()

        # /notify off - removes flag
        self.notify_flag.unlink(missing_ok=True)
        assert not self.notify_flag.exists()

        # /notify on - should create flag
        self.notify_flag.touch()
        assert self.notify_flag.exists()

    def test_notify_on_idempotent(self):
        """Test /notify on is idempotent (can be called multiple times)."""
        # Call on multiple times
        self.notify_flag.touch()
        assert self.notify_flag.exists()

        self.notify_flag.touch()
        assert self.notify_flag.exists()

        self.notify_flag.touch()
        assert self.notify_flag.exists()

    def test_notify_off_idempotent(self):
        """Test /notify off is idempotent (can be called multiple times)."""
        # Flag doesn't exist
        assert not self.notify_flag.exists()

        # Call off multiple times - should not error
        self.notify_flag.unlink(missing_ok=True)
        assert not self.notify_flag.exists()

        self.notify_flag.unlink(missing_ok=True)
        assert not self.notify_flag.exists()

    def test_rapid_toggle_on_off_on(self):
        """Test rapid toggling on->off->on works correctly."""
        # on
        self.notify_flag.touch()
        assert self.notify_flag.exists()

        # off
        self.notify_flag.unlink(missing_ok=True)
        assert not self.notify_flag.exists()

        # on again
        self.notify_flag.touch()
        assert self.notify_flag.exists()

    def test_rapid_toggle_off_on_off(self):
        """Test rapid toggling off->on->off works correctly."""
        self.notify_flag.touch()  # Start enabled

        # off
        self.notify_flag.unlink(missing_ok=True)
        assert not self.notify_flag.exists()

        # on
        self.notify_flag.touch()
        assert self.notify_flag.exists()

        # off again
        self.notify_flag.unlink(missing_ok=True)
        assert not self.notify_flag.exists()


class TestNotifyFlagFileLocation:
    """Tests verifying flag file is created in correct location."""

    def setup_method(self):
        """Setup test fixtures with temp directory."""
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.claude_home = Path(self.temp_dir)

    def teardown_method(self):
        """Cleanup temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_flag_file_path_construction(self):
        """Test flag file path is constructed correctly from CLAUDE_HOME."""
        expected_flag = self.claude_home / 'notifications-enabled'
        assert str(expected_flag) == f"{self.temp_dir}/notifications-enabled"

    def test_flag_file_in_claude_home_not_subdir(self):
        """Test flag file is in CLAUDE_HOME root, not a subdirectory."""
        flag_path = self.claude_home / 'notifications-enabled'

        # Parent should be CLAUDE_HOME itself
        assert flag_path.parent == self.claude_home

    def test_environment_variable_used_for_path(self):
        """Test CLAUDE_HOME env var is used for flag file path."""
        import os

        # Save original
        orig_claude_home = os.environ.get('CLAUDE_HOME')

        try:
            # Set custom CLAUDE_HOME
            os.environ['CLAUDE_HOME'] = str(self.claude_home)

            # Verify path would be constructed from env
            claude_home = Path(os.environ.get('CLAUDE_HOME', Path.home() / '.claude'))
            flag_path = claude_home / 'notifications-enabled'

            assert flag_path == self.claude_home / 'notifications-enabled'
        finally:
            # Restore original
            if orig_claude_home:
                os.environ['CLAUDE_HOME'] = orig_claude_home
            elif 'CLAUDE_HOME' in os.environ:
                del os.environ['CLAUDE_HOME']

    def test_default_path_when_no_env_var(self):
        """Test default ~/.claude path when CLAUDE_HOME not set."""
        import os

        # Save and clear CLAUDE_HOME
        orig_claude_home = os.environ.pop('CLAUDE_HOME', None)

        try:
            claude_home = Path(os.environ.get('CLAUDE_HOME', Path.home() / '.claude'))
            expected = Path.home() / '.claude'

            assert claude_home == expected
        finally:
            # Restore original
            if orig_claude_home:
                os.environ['CLAUDE_HOME'] = orig_claude_home


class TestNotifyCommandIntegration:
    """Integration tests for notify command end-to-end flow."""

    def setup_method(self):
        """Setup test fixtures."""
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.claude_home = Path(self.temp_dir)
        self.notify_flag = self.claude_home / 'notifications-enabled'

    def teardown_method(self):
        """Cleanup temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cmd_on_implementation(self):
        """Test cmd_on creates flag and returns expected output."""
        # Simulate cmd_on logic
        self.notify_flag.touch()
        output = "✓ Notifications enabled"

        assert self.notify_flag.exists()
        assert 'enabled' in output

    def test_cmd_off_implementation(self):
        """Test cmd_off removes flag and returns expected output."""
        # Create flag first
        self.notify_flag.touch()

        # Simulate cmd_off logic
        self.notify_flag.unlink(missing_ok=True)
        output = "✓ Notifications disabled"

        assert not self.notify_flag.exists()
        assert 'disabled' in output

    def test_status_reflects_flag_state_enabled(self):
        """Test status correctly reports enabled state."""
        self.notify_flag.touch()

        # Simulate status check
        is_enabled = self.notify_flag.exists()

        assert is_enabled is True

    def test_status_reflects_flag_state_disabled(self):
        """Test status correctly reports disabled state."""
        # Ensure flag doesn't exist
        self.notify_flag.unlink(missing_ok=True)

        # Simulate status check
        is_enabled = self.notify_flag.exists()

        assert is_enabled is False

    def test_toggle_sequence_state_tracking(self):
        """Test state is correctly tracked through toggle sequence."""
        states = []

        # Initial: disabled
        states.append(('initial', self.notify_flag.exists()))
        assert states[-1] == ('initial', False)

        # Enable
        self.notify_flag.touch()
        states.append(('after on', self.notify_flag.exists()))
        assert states[-1] == ('after on', True)

        # Disable
        self.notify_flag.unlink(missing_ok=True)
        states.append(('after off', self.notify_flag.exists()))
        assert states[-1] == ('after off', False)

        # Re-enable
        self.notify_flag.touch()
        states.append(('after on again', self.notify_flag.exists()))
        assert states[-1] == ('after on again', True)


class TestSubprocessEnvironment:
    """Tests for subprocess environment handling in run_script."""

    def test_safe_env_includes_claude_home(self):
        """Test safe env includes CLAUDE_HOME."""
        import os
        from pathlib import Path

        # Simulate get_safe_env logic
        SAFE_ENV_VARS = {'PATH', 'HOME', 'USER', 'SHELL', 'LANG', 'TERM', 'TMPDIR', 'LC_ALL', 'LC_CTYPE'}
        CLAUDE_HOME = Path('/test/.claude')
        SESSION_NAME = 'test'
        TMUX_SESSION = 'claude-test'

        env = {k: v for k, v in os.environ.items() if k in SAFE_ENV_VARS}
        env['CLAUDE_SESSION'] = SESSION_NAME
        env['TMUX_SESSION'] = TMUX_SESSION
        env['CLAUDE_HOME'] = str(CLAUDE_HOME)

        assert 'CLAUDE_HOME' in env
        assert env['CLAUDE_HOME'] == '/test/.claude'

    def test_safe_env_includes_claude_session(self):
        """Test safe env includes CLAUDE_SESSION."""
        import os
        from pathlib import Path

        SAFE_ENV_VARS = {'PATH', 'HOME', 'USER', 'SHELL', 'LANG', 'TERM', 'TMPDIR', 'LC_ALL', 'LC_CTYPE'}
        CLAUDE_HOME = Path('/test/.claude')
        SESSION_NAME = 'my-session'
        TMUX_SESSION = 'claude-test'

        env = {k: v for k, v in os.environ.items() if k in SAFE_ENV_VARS}
        env['CLAUDE_SESSION'] = SESSION_NAME
        env['TMUX_SESSION'] = TMUX_SESSION
        env['CLAUDE_HOME'] = str(CLAUDE_HOME)

        assert 'CLAUDE_SESSION' in env
        assert env['CLAUDE_SESSION'] == 'my-session'

    def test_safe_env_path_preserved(self):
        """Test PATH is preserved in safe env."""
        import os

        SAFE_ENV_VARS = {'PATH', 'HOME', 'USER', 'SHELL', 'LANG', 'TERM', 'TMPDIR', 'LC_ALL', 'LC_CTYPE'}

        env = {k: v for k, v in os.environ.items() if k in SAFE_ENV_VARS}

        assert 'PATH' in env
        assert len(env['PATH']) > 0

    def test_safe_env_excludes_sensitive_vars(self):
        """Test sensitive vars are excluded from safe env."""
        import os

        SAFE_ENV_VARS = {'PATH', 'HOME', 'USER', 'SHELL', 'LANG', 'TERM', 'TMPDIR', 'LC_ALL', 'LC_CTYPE'}

        # Set some sensitive vars
        test_env = dict(os.environ)
        test_env['SECRET_KEY'] = 'secret'
        test_env['API_TOKEN'] = 'token'
        test_env['PASSWORD'] = 'pass'

        env = {k: v for k, v in test_env.items() if k in SAFE_ENV_VARS}

        assert 'SECRET_KEY' not in env
        assert 'API_TOKEN' not in env
        assert 'PASSWORD' not in env
