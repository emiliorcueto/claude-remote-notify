"""
Unit tests for cancel_pending_notification() in telegram-listener.py.
Tests the Python cancel function and its integration with inject functions.
"""

import os
import sys
import signal
import tempfile
import importlib.util
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

import pytest

# Mock the requests module before importing
mock_requests = MagicMock()
sys.modules['requests'] = mock_requests

# Load telegram-listener.py as a module
HOOKS_DIR = Path(__file__).parent.parent / 'hooks'
spec = importlib.util.spec_from_file_location("telegram_listener", HOOKS_DIR / "telegram-listener.py")
telegram_listener = importlib.util.module_from_spec(spec)
sys.modules['telegram_listener'] = telegram_listener
telegram_listener.__name__ = 'telegram_listener'
spec.loader.exec_module(telegram_listener)

cancel_pending_notification = telegram_listener.cancel_pending_notification


class TestCancelPendingNotification:
    """Tests for the Python cancel_pending_notification() function."""

    def setup_method(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.pending_dir = self.temp_dir / 'notifications-pending'
        self.pending_dir.mkdir(parents=True)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cancel_with_live_process(self):
        """Kill a running background process via PID file."""
        # Spawn a sleep process
        proc = subprocess.Popen(['sleep', '30'])
        pid_file = self.pending_dir / 'test-session.pid'
        pid_file.write_text(str(proc.pid))

        cancel_pending_notification('test-session', self.temp_dir)

        # PID file should be removed
        assert not pid_file.exists()

        # Process should be terminated
        proc.wait(timeout=2)
        assert proc.returncode is not None

    def test_cancel_with_stale_pid(self):
        """Handle a PID file referencing a dead process."""
        pid_file = self.pending_dir / 'test-session.pid'
        pid_file.write_text('99999999')

        cancel_pending_notification('test-session', self.temp_dir)

        assert not pid_file.exists()

    def test_cancel_with_no_pid_file(self):
        """No-op when PID file does not exist."""
        # Should not raise
        cancel_pending_notification('nonexistent', self.temp_dir)

    def test_cancel_with_empty_pid_file(self):
        """Handle an empty PID file gracefully."""
        pid_file = self.pending_dir / 'test-session.pid'
        pid_file.write_text('')

        cancel_pending_notification('test-session', self.temp_dir)

        assert not pid_file.exists()

    def test_cancel_with_corrupt_pid_file(self):
        """Handle non-numeric PID file content."""
        pid_file = self.pending_dir / 'test-session.pid'
        pid_file.write_text('not-a-number')

        cancel_pending_notification('test-session', self.temp_dir)

        assert not pid_file.exists()

    def test_cancel_with_whitespace_pid(self):
        """Handle PID file with trailing whitespace/newlines."""
        proc = subprocess.Popen(['sleep', '30'])
        pid_file = self.pending_dir / 'test-session.pid'
        pid_file.write_text(f'  {proc.pid}\n')

        cancel_pending_notification('test-session', self.temp_dir)

        assert not pid_file.exists()
        proc.wait(timeout=2)
        assert proc.returncode is not None

    def test_cancel_uses_default_claude_home(self):
        """Falls back to CLAUDE_HOME when no path given."""
        pid_file = self.pending_dir / 'test-session.pid'
        pid_file.write_text('99999999')

        with patch.object(telegram_listener, 'CLAUDE_HOME', self.temp_dir):
            cancel_pending_notification('test-session')

        assert not pid_file.exists()

    def test_cancel_missing_pending_dir(self):
        """No-op when notifications-pending directory doesn't exist."""
        empty_dir = self.temp_dir / 'empty'
        empty_dir.mkdir()

        # Should not raise even though notifications-pending/ doesn't exist
        cancel_pending_notification('test-session', empty_dir)


class TestInjectCancelsNotification:
    """Tests that inject functions call cancel_pending_notification."""

    def test_inject_to_tmux_session_cancels(self):
        """inject_to_tmux_session() cancels pending notification on success."""
        from telegram_listener import SessionState

        session = SessionState(
            name='test-session',
            topic_id='123',
            tmux_session='claude-test',
            chat_id='-100123456',
            bot_token='123:ABC'
        )

        with patch.object(telegram_listener, 'tmux_session_exists_for', return_value=True), \
             patch.object(telegram_listener, 'subprocess') as mock_sub, \
             patch.object(telegram_listener, 'cancel_pending_notification') as mock_cancel:
            mock_sub.run.return_value = MagicMock(returncode=0)
            mock_sub.CalledProcessError = subprocess.CalledProcessError

            result = telegram_listener.inject_to_tmux_session(session, 'hello')

            assert result is True
            mock_cancel.assert_called_once_with('test-session')

    def test_inject_to_tmux_session_no_cancel_on_failure(self):
        """inject_to_tmux_session() does NOT cancel when injection fails."""
        from telegram_listener import SessionState

        session = SessionState(
            name='test-session',
            topic_id='123',
            tmux_session='claude-test',
            chat_id='-100123456',
            bot_token='123:ABC'
        )

        with patch.object(telegram_listener, 'tmux_session_exists_for', return_value=False), \
             patch.object(telegram_listener, 'cancel_pending_notification') as mock_cancel:

            result = telegram_listener.inject_to_tmux_session(session, 'hello')

            assert result is False
            mock_cancel.assert_not_called()

    def test_inject_to_tmux_cancels(self):
        """inject_to_tmux() cancels pending notification on success."""
        with patch.object(telegram_listener, 'tmux_session_exists', return_value=True), \
             patch.object(telegram_listener, 'subprocess') as mock_sub, \
             patch.object(telegram_listener, 'cancel_pending_notification') as mock_cancel:
            mock_sub.run.return_value = MagicMock(returncode=0)
            mock_sub.CalledProcessError = subprocess.CalledProcessError

            result = telegram_listener.inject_to_tmux('hello')

            assert result is True
            mock_cancel.assert_called_once()

    def test_inject_to_tmux_no_cancel_on_failure(self):
        """inject_to_tmux() does NOT cancel when injection fails."""
        with patch.object(telegram_listener, 'tmux_session_exists', return_value=False), \
             patch.object(telegram_listener, 'cancel_pending_notification') as mock_cancel:

            result = telegram_listener.inject_to_tmux('hello')

            assert result is False
            mock_cancel.assert_not_called()
