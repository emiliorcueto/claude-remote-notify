"""
Unit tests for startup guard and offset tracking (deduplication).
Tests check_existing_listener, find_old_single_session_listeners,
OffsetTracker, and prompt_cleanup_old_listeners.
"""

import json
import os
import sys
import tempfile
import shutil
import importlib.util
from pathlib import Path
from unittest.mock import patch, MagicMock, call

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

# Import what we need
is_process_running = telegram_listener.is_process_running
check_existing_listener = telegram_listener.check_existing_listener
find_old_single_session_listeners = telegram_listener.find_old_single_session_listeners
prompt_cleanup_old_listeners = telegram_listener.prompt_cleanup_old_listeners
OffsetTracker = telegram_listener.OffsetTracker
CLAUDE_HOME = telegram_listener.CLAUDE_HOME


@pytest.fixture
def tmp_claude_home(tmp_path):
    """Create a temporary CLAUDE_HOME structure."""
    pids_dir = tmp_path / 'pids'
    pids_dir.mkdir()
    state_dir = tmp_path / 'state'
    state_dir.mkdir()
    logs_dir = tmp_path / 'logs'
    logs_dir.mkdir()
    return tmp_path


class TestIsProcessRunning:
    """Tests for is_process_running."""

    def test_current_process_is_running(self):
        assert is_process_running(os.getpid()) is True

    def test_nonexistent_pid(self):
        # Use a very high PID that's unlikely to exist
        assert is_process_running(99999999) is False

    def test_invalid_pid(self):
        with patch('os.kill', side_effect=OSError):
            assert is_process_running(-1) is False


class TestCheckExistingListener:
    """Tests for check_existing_listener."""

    def test_no_pid_file(self, tmp_claude_home):
        """No PID file means startup should proceed."""
        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home):
            assert check_existing_listener() is True

    def test_stale_pid_file_removed(self, tmp_claude_home):
        """Stale PID file (dead process) should be removed."""
        pid_file = tmp_claude_home / 'pids' / 'listener-multi.pid'
        pid_file.write_text('99999999')

        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home):
            assert check_existing_listener() is True
            assert not pid_file.exists()

    def test_empty_pid_file_removed(self, tmp_claude_home):
        """Empty PID file should be removed."""
        pid_file = tmp_claude_home / 'pids' / 'listener-multi.pid'
        pid_file.write_text('')

        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home):
            assert check_existing_listener() is True
            assert not pid_file.exists()

    def test_own_pid_allowed(self, tmp_claude_home):
        """Our own PID should not block startup (restart scenario)."""
        pid_file = tmp_claude_home / 'pids' / 'listener-multi.pid'
        pid_file.write_text(str(os.getpid()))

        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home):
            assert check_existing_listener() is True

    def test_running_process_blocks(self, tmp_claude_home):
        """Running process with different PID should block startup."""
        pid_file = tmp_claude_home / 'pids' / 'listener-multi.pid'
        # PID 1 (init/launchd) is always running
        pid_file.write_text('1')

        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home):
            assert check_existing_listener() is False

    def test_corrupt_pid_file(self, tmp_claude_home):
        """Corrupt PID file should be removed and startup allowed."""
        pid_file = tmp_claude_home / 'pids' / 'listener-multi.pid'
        pid_file.write_text('not-a-number')

        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home):
            assert check_existing_listener() is True
            assert not pid_file.exists()


class TestFindOldSingleSessionListeners:
    """Tests for find_old_single_session_listeners."""

    def test_no_pids_dir(self, tmp_claude_home):
        """Missing pids dir returns empty list."""
        shutil.rmtree(tmp_claude_home / 'pids')
        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home):
            assert find_old_single_session_listeners() == []

    def test_no_old_listeners(self, tmp_claude_home):
        """No PID files means no old listeners."""
        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home):
            assert find_old_single_session_listeners() == []

    def test_skips_multi_pid(self, tmp_claude_home):
        """Multi-session PID file should be skipped."""
        pid_file = tmp_claude_home / 'pids' / 'listener-multi.pid'
        pid_file.write_text(str(os.getpid()))

        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home):
            assert find_old_single_session_listeners() == []

    def test_finds_running_old_listener(self, tmp_claude_home):
        """Should find running old single-session listener."""
        pid_file = tmp_claude_home / 'pids' / 'listener-NotaryGuide.pid'
        # PID 1 is always running
        pid_file.write_text('1')

        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home):
            result = find_old_single_session_listeners()
            assert len(result) == 1
            assert result[0] == (1, 'NotaryGuide')

    def test_ignores_dead_old_listener(self, tmp_claude_home):
        """Dead old listener PID files should be ignored."""
        pid_file = tmp_claude_home / 'pids' / 'listener-OldSession.pid'
        pid_file.write_text('99999999')

        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home):
            assert find_old_single_session_listeners() == []

    def test_multiple_old_listeners(self, tmp_claude_home):
        """Should find multiple running old listeners."""
        for name in ['NotaryGuide', 'PleiPlatform']:
            pid_file = tmp_claude_home / 'pids' / f'listener-{name}.pid'
            pid_file.write_text('1')

        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home):
            result = find_old_single_session_listeners()
            assert len(result) == 2
            names = {name for _, name in result}
            assert names == {'NotaryGuide', 'PleiPlatform'}


class TestPromptCleanupOldListeners:
    """Tests for prompt_cleanup_old_listeners."""

    def test_skip_cleanup(self, tmp_claude_home):
        """User choosing '2' should skip cleanup."""
        old_listeners = [(1234, 'TestSession')]

        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home), \
             patch('builtins.input', return_value='2'):
            # Create a dummy cleanup script
            hooks_dir = tmp_claude_home / 'hooks'
            hooks_dir.mkdir(exist_ok=True)
            script = hooks_dir / 'cleanup-old-listeners.sh'
            script.write_text('#!/bin/bash\necho done')
            script.chmod(0o755)

            result = prompt_cleanup_old_listeners(old_listeners)
            assert result is True

    def test_run_cleanup(self, tmp_claude_home):
        """User choosing '1' should run cleanup script."""
        old_listeners = [(1234, 'TestSession')]

        hooks_dir = tmp_claude_home / 'hooks'
        hooks_dir.mkdir(exist_ok=True)
        script = hooks_dir / 'cleanup-old-listeners.sh'
        script.write_text('#!/bin/bash\necho "Cleanup done"')
        script.chmod(0o755)

        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home), \
             patch('builtins.input', return_value='1'):
            result = prompt_cleanup_old_listeners(old_listeners)
            assert result is True

    def test_eof_defaults_to_skip(self, tmp_claude_home):
        """EOFError during input should default to skip."""
        old_listeners = [(1234, 'TestSession')]

        hooks_dir = tmp_claude_home / 'hooks'
        hooks_dir.mkdir(exist_ok=True)
        script = hooks_dir / 'cleanup-old-listeners.sh'
        script.write_text('#!/bin/bash\necho done')
        script.chmod(0o755)

        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home), \
             patch('builtins.input', side_effect=EOFError):
            result = prompt_cleanup_old_listeners(old_listeners)
            assert result is True

    def test_no_cleanup_script(self, tmp_claude_home):
        """Missing cleanup script should show manual instructions."""
        old_listeners = [(1234, 'TestSession')]

        with patch.object(telegram_listener, 'CLAUDE_HOME', tmp_claude_home):
            result = prompt_cleanup_old_listeners(old_listeners)
            assert result is True


class TestOffsetTracker:
    """Tests for OffsetTracker (deduplication)."""

    def test_new_tracker_empty(self, tmp_claude_home):
        """New tracker with no file should be empty."""
        filepath = tmp_claude_home / 'state' / 'listener-offsets.json'
        tracker = OffsetTracker(filepath=filepath)
        assert not tracker.is_duplicate(123)

    def test_track_and_detect_duplicate(self, tmp_claude_home):
        """Tracked update should be detected as duplicate."""
        filepath = tmp_claude_home / 'state' / 'listener-offsets.json'
        tracker = OffsetTracker(filepath=filepath)

        tracker.track(100)
        assert tracker.is_duplicate(100)
        assert not tracker.is_duplicate(101)

    def test_save_and_reload(self, tmp_claude_home):
        """Offsets should persist across tracker instances."""
        filepath = tmp_claude_home / 'state' / 'listener-offsets.json'
        tracker = OffsetTracker(filepath=filepath)

        tracker.track(200)
        tracker.track(201)
        tracker.save()

        # Reload
        tracker2 = OffsetTracker(filepath=filepath)
        assert tracker2.is_duplicate(200)
        assert tracker2.is_duplicate(201)
        assert not tracker2.is_duplicate(202)

    def test_rotation(self, tmp_claude_home):
        """Tracker should rotate old entries when max_tracked is reached."""
        filepath = tmp_claude_home / 'state' / 'listener-offsets.json'
        tracker = OffsetTracker(filepath=filepath, max_tracked=5)

        for i in range(10):
            tracker.track(i)

        # Oldest entries should have been rotated out
        assert not tracker.is_duplicate(0)
        assert not tracker.is_duplicate(4)
        # Recent entries should still be there
        assert tracker.is_duplicate(5)
        assert tracker.is_duplicate(9)

    def test_auto_save_interval(self, tmp_claude_home):
        """Tracker should auto-save after OFFSET_SAVE_INTERVAL updates."""
        filepath = tmp_claude_home / 'state' / 'listener-offsets.json'
        tracker = OffsetTracker(filepath=filepath, max_tracked=200)

        # Override save interval for testing
        original_interval = telegram_listener.OFFSET_SAVE_INTERVAL
        telegram_listener.OFFSET_SAVE_INTERVAL = 5

        try:
            for i in range(5):
                tracker.track(i)

            # Should have auto-saved
            assert filepath.exists()
            data = json.loads(filepath.read_text())
            assert len(data['offsets']) == 5
        finally:
            telegram_listener.OFFSET_SAVE_INTERVAL = original_interval

    def test_corrupt_file_handled(self, tmp_claude_home):
        """Corrupt offset file should not crash tracker."""
        filepath = tmp_claude_home / 'state' / 'listener-offsets.json'
        filepath.write_text('not valid json')

        tracker = OffsetTracker(filepath=filepath)
        assert not tracker.is_duplicate(100)
        tracker.track(100)
        assert tracker.is_duplicate(100)

    def test_save_creates_directory(self, tmp_claude_home):
        """Save should create state directory if missing."""
        state_dir = tmp_claude_home / 'state'
        shutil.rmtree(state_dir)

        filepath = state_dir / 'listener-offsets.json'
        tracker = OffsetTracker(filepath=filepath)
        tracker.track(100)
        tracker.save()

        assert filepath.exists()

    def test_duplicate_track_idempotent(self, tmp_claude_home):
        """Tracking same ID twice should not grow the list."""
        filepath = tmp_claude_home / 'state' / 'listener-offsets.json'
        tracker = OffsetTracker(filepath=filepath)

        tracker.track(100)
        tracker.track(100)
        assert len(tracker.seen_offsets) == 1

    def test_save_file_format(self, tmp_claude_home):
        """Verify the saved JSON structure."""
        filepath = tmp_claude_home / 'state' / 'listener-offsets.json'
        tracker = OffsetTracker(filepath=filepath)

        tracker.track(100)
        tracker.track(200)
        tracker.save()

        data = json.loads(filepath.read_text())
        assert 'offsets' in data
        assert 'last_saved' in data
        assert data['offsets'] == [100, 200]
        assert isinstance(data['last_saved'], int)
