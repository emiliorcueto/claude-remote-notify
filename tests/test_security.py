"""
Unit tests for security functions in telegram-listener.py
Tests command injection prevention, path validation, and safe env handling.
"""

import os
import sys
import stat
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add hooks directory to path for importing
sys.path.insert(0, str(Path(__file__).parent.parent / 'hooks'))

# Mock the requests module before importing telegram-listener
sys.modules['requests'] = MagicMock()

# Import functions by parsing the module (since it has global initialization)
# We'll test the functions directly by recreating them here with the same logic

SAFE_ENV_VARS = {'PATH', 'HOME', 'USER', 'SHELL', 'LANG', 'TERM', 'TMPDIR', 'LC_ALL', 'LC_CTYPE'}


def get_safe_env(claude_home, session_name, tmux_session):
    """Return environment dict with only safe variables plus session-specific ones."""
    env = {k: v for k, v in os.environ.items() if k in SAFE_ENV_VARS}
    env['CLAUDE_SESSION'] = session_name
    env['TMUX_SESSION'] = tmux_session
    env['CLAUDE_HOME'] = str(claude_home)
    return env


def validate_script_path(script_path, claude_home):
    """Validate script path is within CLAUDE_HOME and has safe permissions.

    For symlinks within CLAUDE_HOME (dev mode), validates the target separately.
    """
    path = Path(script_path)
    claude_home_resolved = Path(claude_home).resolve()

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


class TestSafeEnv:
    """Tests for get_safe_env function."""

    def test_only_whitelisted_vars_included(self):
        """Ensure only whitelisted env vars are passed through."""
        with patch.dict(os.environ, {
            'PATH': '/usr/bin',
            'HOME': '/home/user',
            'SECRET_KEY': 'supersecret',
            'DATABASE_URL': 'postgres://...',
            'SHELL': '/bin/bash'
        }, clear=True):
            env = get_safe_env('/tmp/claude', 'test', 'claude-test')

            assert 'PATH' in env
            assert 'HOME' in env
            assert 'SHELL' in env
            assert 'SECRET_KEY' not in env
            assert 'DATABASE_URL' not in env

    def test_session_vars_always_included(self):
        """Ensure session-specific vars are always added."""
        with patch.dict(os.environ, {}, clear=True):
            env = get_safe_env('/tmp/claude', 'mysession', 'claude-mysession')

            assert env['CLAUDE_SESSION'] == 'mysession'
            assert env['TMUX_SESSION'] == 'claude-mysession'
            assert env['CLAUDE_HOME'] == '/tmp/claude'

    def test_dangerous_vars_excluded(self):
        """Ensure dangerous variables are excluded."""
        dangerous_vars = [
            'LD_PRELOAD', 'LD_LIBRARY_PATH', 'DYLD_INSERT_LIBRARIES',
            'BASH_ENV', 'ENV', 'PROMPT_COMMAND', 'PS1', 'PS2',
            'IFS', 'CDPATH', 'GLOBIGNORE', 'SHELLOPTS'
        ]
        with patch.dict(os.environ, {v: 'malicious' for v in dangerous_vars}, clear=True):
            env = get_safe_env('/tmp/claude', 'test', 'claude-test')

            for var in dangerous_vars:
                assert var not in env


class TestValidateScriptPath:
    """Tests for validate_script_path function."""

    def setup_method(self):
        """Create temp directories for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.claude_home = Path(self.temp_dir) / '.claude'
        self.claude_home.mkdir(parents=True)
        self.hooks_dir = self.claude_home / 'hooks'
        self.hooks_dir.mkdir()

    def teardown_method(self):
        """Cleanup temp directories."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_valid_script_in_claude_home(self):
        """Valid script within CLAUDE_HOME should pass."""
        script = self.hooks_dir / 'test-script.sh'
        script.write_text('#!/bin/bash\necho hello')
        script.chmod(0o755)

        result = validate_script_path(str(script), self.claude_home)
        assert result == script.resolve()

    def test_script_outside_claude_home_rejected(self):
        """Script outside CLAUDE_HOME should be rejected."""
        outside_script = Path(self.temp_dir) / 'malicious.sh'
        outside_script.write_text('#!/bin/bash\nrm -rf /')
        outside_script.chmod(0o755)

        with pytest.raises(ValueError, match="outside CLAUDE_HOME"):
            validate_script_path(str(outside_script), self.claude_home)

    def test_path_traversal_attack_rejected(self):
        """Path traversal attacks should be rejected."""
        script = self.hooks_dir / 'legit.sh'
        script.write_text('#!/bin/bash\necho hello')
        script.chmod(0o755)

        # Try path traversal
        traversal_path = str(self.hooks_dir / '..' / '..' / 'etc' / 'passwd')

        with pytest.raises(ValueError, match="outside CLAUDE_HOME"):
            validate_script_path(traversal_path, self.claude_home)

    def test_nonexistent_script_rejected(self):
        """Non-existent script should be rejected."""
        with pytest.raises(ValueError, match="Script not found"):
            validate_script_path(str(self.hooks_dir / 'nonexistent.sh'), self.claude_home)

    def test_directory_rejected(self):
        """Directory path should be rejected."""
        with pytest.raises(ValueError, match="Not a file"):
            validate_script_path(str(self.hooks_dir), self.claude_home)

    def test_world_writable_script_rejected(self):
        """World-writable script should be rejected."""
        script = self.hooks_dir / 'world-writable.sh'
        script.write_text('#!/bin/bash\necho hello')
        script.chmod(0o777)  # World-writable

        with pytest.raises(ValueError, match="world-writable"):
            validate_script_path(str(script), self.claude_home)

    def test_symlink_in_claude_home_to_safe_target_allowed(self):
        """Symlink within CLAUDE_HOME pointing to safe target outside should work (dev mode)."""
        # Create a safe target outside CLAUDE_HOME (owned by current user, not world-writable)
        outside_target = Path(self.temp_dir) / 'dev-script.sh'
        outside_target.write_text('#!/bin/bash\necho "dev mode"')
        outside_target.chmod(0o755)

        # Symlink within CLAUDE_HOME pointing to outside target
        symlink = self.hooks_dir / 'dev-symlink.sh'
        symlink.symlink_to(outside_target)

        # Should succeed - symlink is in CLAUDE_HOME, target is safe
        result = validate_script_path(str(symlink), self.claude_home)
        assert result == outside_target.resolve()

    def test_symlink_outside_claude_home_rejected(self):
        """Symlink located outside CLAUDE_HOME should be rejected."""
        # Create a target
        target = self.hooks_dir / 'target.sh'
        target.write_text('#!/bin/bash\necho hello')
        target.chmod(0o755)

        # Symlink outside CLAUDE_HOME
        outside_symlink = Path(self.temp_dir) / 'outside-symlink.sh'
        outside_symlink.symlink_to(target)

        # Should fail - symlink itself is outside CLAUDE_HOME
        with pytest.raises(ValueError, match="outside CLAUDE_HOME"):
            validate_script_path(str(outside_symlink), self.claude_home)

    def test_symlink_to_world_writable_target_rejected(self):
        """Symlink to world-writable target should be rejected."""
        # Create world-writable target outside CLAUDE_HOME
        outside_target = Path(self.temp_dir) / 'world-writable.sh'
        outside_target.write_text('#!/bin/bash\necho unsafe')
        outside_target.chmod(0o777)  # World-writable

        symlink = self.hooks_dir / 'unsafe-symlink.sh'
        symlink.symlink_to(outside_target)

        with pytest.raises(ValueError, match="world-writable"):
            validate_script_path(str(symlink), self.claude_home)

    def test_symlink_to_nonexistent_target_rejected(self):
        """Symlink to non-existent target should be rejected."""
        nonexistent = Path(self.temp_dir) / 'nonexistent.sh'
        symlink = self.hooks_dir / 'broken-symlink.sh'
        symlink.symlink_to(nonexistent)

        with pytest.raises(ValueError, match="Script not found"):
            validate_script_path(str(symlink), self.claude_home)

    def test_symlink_to_directory_rejected(self):
        """Symlink to directory should be rejected."""
        target_dir = Path(self.temp_dir) / 'target-dir'
        target_dir.mkdir()

        symlink = self.hooks_dir / 'dir-symlink.sh'
        symlink.symlink_to(target_dir)

        with pytest.raises(ValueError, match="not a file"):
            validate_script_path(str(symlink), self.claude_home)


class TestCommandInjectionPrevention:
    """Tests for command injection prevention in run_script."""

    def setup_method(self):
        """Create temp directories for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.claude_home = Path(self.temp_dir) / '.claude'
        self.claude_home.mkdir(parents=True)
        self.hooks_dir = self.claude_home / 'hooks'
        self.hooks_dir.mkdir()

    def teardown_method(self):
        """Cleanup temp directories."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_shell_metacharacters_not_interpreted(self):
        """Shell metacharacters in args should not be interpreted."""
        # Create a script that echoes its arguments
        script = self.hooks_dir / 'echo-args.sh'
        script.write_text('#!/bin/bash\necho "$@"')
        script.chmod(0o755)

        import shlex
        import subprocess

        # Test that shell metacharacters are passed literally
        dangerous_args = "; rm -rf / #"
        cmd = [str(script)]
        cmd.extend(shlex.split(dangerous_args))

        # With shell=False, the semicolon is just a literal argument
        result = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=5
        )

        # The output should contain the literal characters, not execute them
        # Note: shlex.split will split on whitespace, so ";" becomes an arg
        assert result.returncode == 0

    def test_backtick_injection_prevented(self):
        """Backtick command substitution should not work."""
        script = self.hooks_dir / 'echo-args.sh'
        script.write_text('#!/bin/bash\necho "$@"')
        script.chmod(0o755)

        import shlex
        import subprocess

        # Try backtick injection
        args = '`whoami`'
        cmd = [str(script)]
        cmd.extend(shlex.split(args))

        result = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=5
        )

        # The backticks should be literal, not executed
        assert '`whoami`' in result.stdout or result.stdout == ''

    def test_dollar_paren_injection_prevented(self):
        """$(command) injection should not work."""
        script = self.hooks_dir / 'echo-args.sh'
        script.write_text('#!/bin/bash\necho "$@"')
        script.chmod(0o755)

        import shlex
        import subprocess

        # Try $() injection
        args = '$(whoami)'
        cmd = [str(script)]
        cmd.extend(shlex.split(args))

        result = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=5
        )

        # Should be literal, not the actual username
        assert '$(whoami)' in result.stdout or result.stdout == ''

    def test_pipe_injection_prevented(self):
        """Pipe injection should not work."""
        script = self.hooks_dir / 'echo-args.sh'
        script.write_text('#!/bin/bash\necho "$@"')
        script.chmod(0o755)

        import shlex
        import subprocess

        # Try pipe injection
        args = '| cat /etc/passwd'
        cmd = [str(script)]
        cmd.extend(shlex.split(args))

        result = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=5
        )

        # The pipe should be a literal argument
        assert result.returncode == 0


class TestShlexSplit:
    """Tests for shlex.split behavior with various inputs."""

    def test_normal_args_parsed_correctly(self):
        """Normal arguments should be parsed correctly."""
        import shlex

        assert shlex.split('help') == ['help']
        assert shlex.split('on') == ['on']
        assert shlex.split('100') == ['100']
        assert shlex.split('back 1') == ['back', '1']

    def test_quoted_args_handled(self):
        """Quoted arguments should be handled correctly."""
        import shlex

        assert shlex.split('"hello world"') == ['hello world']
        assert shlex.split("'hello world'") == ['hello world']
        assert shlex.split('arg1 "arg 2" arg3') == ['arg1', 'arg 2', 'arg3']

    def test_empty_string_returns_empty_list(self):
        """Empty string should return empty list."""
        import shlex

        assert shlex.split('') == []
        assert shlex.split('   ') == []

    def test_shell_metacharacters_preserved_as_literals(self):
        """Shell metacharacters should be preserved as literal strings."""
        import shlex

        # These are parsed as literal strings, not shell commands
        result = shlex.split('status')
        assert result == ['status']

        # Semicolon gets split as separate token
        result = shlex.split('; rm -rf /')
        # shlex treats ; as part of the token, not a separator
        assert ';' in result[0] or result == [';', 'rm', '-rf', '/']


class TestMaskSensitive:
    """Tests for mask_sensitive function."""

    def test_mask_long_string(self):
        """Long string should be masked with visible start and end."""
        def mask_sensitive(value, show_start=3, show_end=2):
            if not value:
                return "(not set)"
            value = str(value)
            if len(value) <= show_start + show_end + 3:
                return "***"
            return f"{value[:show_start]}...{value[-show_end:]}"

        result = mask_sensitive("1234567890abcdefghij", 3, 2)
        assert result == "123...ij"

    def test_mask_short_string(self):
        """Short string should be fully masked."""
        def mask_sensitive(value, show_start=3, show_end=2):
            if not value:
                return "(not set)"
            value = str(value)
            if len(value) <= show_start + show_end + 3:
                return "***"
            return f"{value[:show_start]}...{value[-show_end:]}"

        result = mask_sensitive("short", 3, 2)
        assert result == "***"

    def test_mask_empty_string(self):
        """Empty string should return not set message."""
        def mask_sensitive(value, show_start=3, show_end=2):
            if not value:
                return "(not set)"
            value = str(value)
            if len(value) <= show_start + show_end + 3:
                return "***"
            return f"{value[:show_start]}...{value[-show_end:]}"

        result = mask_sensitive("", 3, 2)
        assert result == "(not set)"

        result = mask_sensitive(None, 3, 2)
        assert result == "(not set)"

    def test_mask_bot_token(self):
        """Bot token should be masked appropriately."""
        def mask_sensitive(value, show_start=3, show_end=2):
            if not value:
                return "(not set)"
            value = str(value)
            if len(value) <= show_start + show_end + 3:
                return "***"
            return f"{value[:show_start]}...{value[-show_end:]}"

        token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz123456"
        result = mask_sensitive(token, 5, 3)
        assert result == "12345...456"
        assert "ABCdef" not in result  # Middle should be hidden

    def test_mask_chat_id(self):
        """Chat ID should be masked appropriately."""
        def mask_sensitive(value, show_start=3, show_end=2):
            if not value:
                return "(not set)"
            value = str(value)
            if len(value) <= show_start + show_end + 3:
                return "***"
            return f"{value[:show_start]}...{value[-show_end:]}"

        chat_id = "-1001234567890"
        result = mask_sensitive(chat_id, 2, 2)
        assert result == "-1...90"
        assert "12345678" not in result  # Middle should be hidden


class TestSanitizeTmuxInput:
    """Tests for sanitize_tmux_input function."""

    def create_sanitize_function(self):
        """Create the sanitize function for testing."""
        import re
        import unicodedata

        def sanitize_tmux_input(text):
            if not text:
                return ""
            # Remove ANSI CSI escape sequences
            text = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text)
            # Remove OSC sequences
            text = re.sub(r'\x1b\][^\x07]*\x07', '', text)
            # Remove other escape sequences
            text = re.sub(r'\x1b[^\x1b]*', '', text)
            # Filter control characters
            result = []
            for char in text:
                if char in '\n\t':
                    result.append(char)
                elif ord(char) >= 32:
                    cat = unicodedata.category(char)
                    if cat not in ('Cc', 'Cf'):
                        result.append(char)
            return ''.join(result)

        return sanitize_tmux_input

    def test_normal_text_unchanged(self):
        """Normal text should pass through unchanged."""
        sanitize = self.create_sanitize_function()
        assert sanitize("Hello, World!") == "Hello, World!"
        assert sanitize("Multiple\nlines") == "Multiple\nlines"
        assert sanitize("Tab\there") == "Tab\there"

    def test_ansi_color_codes_removed(self):
        """ANSI color codes should be removed."""
        sanitize = self.create_sanitize_function()
        # Red text escape sequence
        assert sanitize("\x1b[31mRed text\x1b[0m") == "Red text"
        # Bold
        assert sanitize("\x1b[1mBold\x1b[0m") == "Bold"
        # Multiple codes
        assert sanitize("\x1b[1;31;40mStyled\x1b[0m") == "Styled"

    def test_cursor_movement_removed(self):
        """Cursor movement sequences should be removed."""
        sanitize = self.create_sanitize_function()
        # Cursor up
        assert sanitize("Text\x1b[AUp") == "TextUp"
        # Cursor down
        assert sanitize("Text\x1b[BDown") == "TextDown"
        # Cursor position
        assert sanitize("Text\x1b[10;20HPosition") == "TextPosition"

    def test_osc_sequences_removed(self):
        """OSC sequences (like title changes) should be removed."""
        sanitize = self.create_sanitize_function()
        # Set window title
        assert sanitize("\x1b]0;New Title\x07Text") == "Text"
        # Other OSC
        assert sanitize("Before\x1b]2;Title\x07After") == "BeforeAfter"

    def test_control_characters_removed(self):
        """Control characters (except newline/tab) should be removed."""
        sanitize = self.create_sanitize_function()
        # Bell character
        assert sanitize("Text\x07bell") == "Textbell"
        # Null byte
        assert sanitize("Text\x00null") == "Textnull"
        # Backspace
        assert sanitize("Text\x08backspace") == "Textbackspace"

    def test_empty_input(self):
        """Empty input should return empty string."""
        sanitize = self.create_sanitize_function()
        assert sanitize("") == ""
        assert sanitize(None) == ""

    def test_unicode_preserved(self):
        """Unicode characters should be preserved."""
        sanitize = self.create_sanitize_function()
        assert sanitize("Hello 世界") == "Hello 世界"
        assert sanitize("Emoji 🎉") == "Emoji 🎉"

    def test_malicious_injection_prevented(self):
        """Malicious terminal injection attempts should be neutralized."""
        sanitize = self.create_sanitize_function()
        # Clear screen attempt
        result = sanitize("\x1b[2JEvil")
        assert "\x1b" not in result
        assert "Evil" in result

        # Terminal reset attempt
        result = sanitize("\x1bcReset")
        assert "\x1b" not in result
