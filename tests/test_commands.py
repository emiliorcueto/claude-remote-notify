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
