"""
Unit tests for /preview command handler in telegram-listener.py.
Verifies no intermediary "Generating preview..." message is sent.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add hooks directory to path for importing
sys.path.insert(0, str(Path(__file__).parent.parent / 'hooks'))

# Mock the requests module before importing
mock_requests = MagicMock()
sys.modules['requests'] = mock_requests


class TestPreviewCommand:
    """Tests for /preview command handler (single-session)."""

    def setup_method(self):
        self.mock_send_message = MagicMock()
        self.mock_run_script = MagicMock()
        self.mock_set_reaction = MagicMock()
        self.mock_log = MagicMock()
        self.session_name = 'test-session'

    def create_handle_command(self, script_exists=True, script_output="✓ Sent to Telegram"):
        session_name = self.session_name
        mock_send = self.mock_send_message
        mock_run = MagicMock(return_value=script_output)
        mock_reaction = self.mock_set_reaction
        mock_log = self.mock_log
        script_path = Path('/mock/hooks/telegram-preview.sh')

        def handle_command(command, from_user, message_id=None):
            parts = command.strip().split()
            cmd = parts[0].lower()
            args = ' '.join(parts[1:]) if len(parts) > 1 else ''

            if cmd == '/preview':
                if not script_exists:
                    mock_send(
                        f"❌ [{session_name}] Preview script not found"
                    )
                    return True

                if args.lower() == 'help':
                    output = mock_run(str(script_path), 'help')
                    mock_send(
                        f"📺 [{session_name}] Preview Help\n\n{output[:3500]}"
                    )
                    return True

                # The preview script sends the file directly to Telegram
                output = mock_run(str(script_path), args)

                if 'Error' in output or 'error' in output.lower():
                    if message_id:
                        mock_reaction(message_id, "😱")
                    mock_send(
                        f"⚠️ [{session_name}] {output[:1000]}"
                    )
                else:
                    if message_id:
                        mock_reaction(message_id, "👀")

                return True

            return False

        return handle_command, mock_send, mock_run, mock_reaction

    def test_preview_success_no_generating_message(self):
        """Preview success must NOT send a 'Generating preview...' message."""
        handle, mock_send, mock_run, mock_reaction = self.create_handle_command(
            script_output="✓ Sent to Telegram\n  Tap the file to view with full colors!"
        )

        result = handle('/preview', 'testuser', message_id=123)

        assert result is True
        mock_run.assert_called_once()
        # No message sent on success - only reaction
        mock_send.assert_not_called()
        mock_reaction.assert_called_once_with(123, "👀")

    def test_preview_success_no_message_id(self):
        """Preview success without message_id - no reaction, no message."""
        handle, mock_send, mock_run, mock_reaction = self.create_handle_command()

        result = handle('/preview', 'testuser')

        assert result is True
        mock_send.assert_not_called()
        mock_reaction.assert_not_called()

    def test_preview_with_line_count(self):
        """Preview with custom line count."""
        handle, mock_send, mock_run, mock_reaction = self.create_handle_command()

        result = handle('/preview 100', 'testuser', message_id=456)

        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
        assert call_args[1] == '100'
        mock_send.assert_not_called()

    def test_preview_error_sends_message(self):
        """Preview error should send error message + 😱 reaction."""
        handle, mock_send, mock_run, mock_reaction = self.create_handle_command(
            script_output="Error: tmux session 'claude-test' not found"
        )

        result = handle('/preview', 'testuser', message_id=789)

        assert result is True
        mock_reaction.assert_called_once_with(789, "😱")
        mock_send.assert_called_once()
        assert "Error" in mock_send.call_args[0][0]

    def test_preview_script_not_found(self):
        """Missing script sends error message."""
        handle, mock_send, mock_run, mock_reaction = self.create_handle_command(
            script_exists=False
        )

        result = handle('/preview', 'testuser')

        assert result is True
        mock_send.assert_called_once()
        assert "not found" in mock_send.call_args[0][0]
        mock_run.assert_not_called()

    def test_preview_help(self):
        """Preview help sends help text as message."""
        handle, mock_send, mock_run, mock_reaction = self.create_handle_command(
            script_output="Preview help text here"
        )

        result = handle('/preview help', 'testuser')

        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
        assert call_args[1] == 'help'
        mock_send.assert_called_once()
        assert "Preview Help" in mock_send.call_args[0][0]

    def test_preview_case_insensitive(self):
        """Preview command is case insensitive."""
        handle, mock_send, mock_run, mock_reaction = self.create_handle_command()

        result = handle('/PREVIEW', 'testuser', message_id=123)

        assert result is True
        mock_send.assert_not_called()
        mock_reaction.assert_called_once_with(123, "👀")

    def test_preview_back_mode(self):
        """Preview with 'back N' args passes them through."""
        handle, mock_send, mock_run, mock_reaction = self.create_handle_command()

        result = handle('/preview back 2', 'testuser', message_id=123)

        assert result is True
        call_args = mock_run.call_args[0]
        assert call_args[1] == 'back 2'


class TestPreviewCommandMultiSession:
    """Tests for /preview command handler (multi-session)."""

    def setup_method(self):
        self.mock_send_message = MagicMock()
        self.mock_run_script = MagicMock()
        self.mock_set_reaction = MagicMock()
        self.session_name = 'multi-test'

    def create_handle_command(self, script_exists=True, script_output="✓ Sent to Telegram"):
        session_name = self.session_name
        mock_send = self.mock_send_message
        mock_run = MagicMock(return_value=script_output)
        mock_reaction = self.mock_set_reaction
        script_path = Path('/mock/hooks/telegram-preview.sh')

        def handle_command_session(command, from_user, message_id, session=None, manager=None):
            parts = command.strip().split()
            cmd = parts[0].lower()
            args = ' '.join(parts[1:]) if len(parts) > 1 else ''

            if cmd == '/preview':
                if not script_exists:
                    mock_send(f"❌ [{session_name}] Preview script not found")
                    return True

                if args.lower() == 'help':
                    output = mock_run(str(script_path), 'help')
                    mock_send(f"📺 [{session_name}] Preview Help\n\n{output[:3500]}")
                    return True

                # The preview script sends the file directly to Telegram
                output = mock_run(str(script_path), args)

                if 'Error' in output or 'error' in output.lower():
                    if message_id:
                        mock_reaction(message_id, "😱")
                    mock_send(f"⚠️ [{session_name}] {output[:1000]}")
                else:
                    if message_id:
                        mock_reaction(message_id, "👀")

                return True

            return False

        return handle_command_session, mock_send, mock_run, mock_reaction

    def test_multi_session_preview_no_generating_message(self):
        """Multi-session preview must NOT send 'Generating preview...' message."""
        handle, mock_send, mock_run, mock_reaction = self.create_handle_command(
            script_output="✓ Sent to Telegram"
        )

        result = handle('/preview', 'testuser', message_id=123)

        assert result is True
        mock_send.assert_not_called()
        mock_reaction.assert_called_once_with(123, "👀")

    def test_multi_session_preview_error(self):
        """Multi-session preview error sends message + reaction."""
        handle, mock_send, mock_run, mock_reaction = self.create_handle_command(
            script_output="Error: something failed"
        )

        result = handle('/preview', 'testuser', message_id=456)

        assert result is True
        mock_reaction.assert_called_once_with(456, "😱")
        mock_send.assert_called_once()

    def test_multi_session_preview_help(self):
        """Multi-session preview help sends help text."""
        handle, mock_send, mock_run, mock_reaction = self.create_handle_command(
            script_output="Help text"
        )

        result = handle('/preview help', 'testuser', message_id=789)

        assert result is True
        mock_send.assert_called_once()
        assert "Preview Help" in mock_send.call_args[0][0]
