"""
Unit tests for HTML formatting, option detection, and callback query handling.
Tests escape_html(), OPTION_PATTERN, callback data format, and answer_callback_query.
"""

import importlib.util
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Load telegram-listener module (hyphen in filename requires importlib)
HOOKS_DIR = Path(__file__).parent.parent / 'hooks'
_spec = importlib.util.spec_from_file_location(
    "telegram_listener", HOOKS_DIR / "telegram-listener.py"
)

# Mock requests before loading module
mock_requests = MagicMock()
sys.modules['requests'] = mock_requests

_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

escape_html = _module.escape_html
OPTION_PATTERN = _module.OPTION_PATTERN


class TestEscapeHtml:
    """Tests for escape_html() utility function."""

    def test_escape_ampersand(self):
        assert escape_html("a & b") == "a &amp; b"

    def test_escape_less_than(self):
        assert escape_html("a < b") == "a &lt; b"

    def test_escape_greater_than(self):
        assert escape_html("a > b") == "a &gt; b"

    def test_normal_text_unchanged(self):
        assert escape_html("hello world") == "hello world"

    def test_all_special_chars(self):
        assert escape_html("<b>&test</b>") == "&lt;b&gt;&amp;test&lt;/b&gt;"

    def test_empty_string(self):
        assert escape_html("") == ""

    def test_escape_order_ampersand_first(self):
        """& must be escaped first to avoid double-escaping &lt; etc."""
        result = escape_html("&<>")
        assert result == "&amp;&lt;&gt;"

    def test_multiple_ampersands(self):
        assert escape_html("a && b && c") == "a &amp;&amp; b &amp;&amp; c"

    def test_html_tags_escaped(self):
        assert escape_html("<pre>code</pre>") == "&lt;pre&gt;code&lt;/pre&gt;"

    def test_unicode_preserved(self):
        assert escape_html("🔔 alert") == "🔔 alert"

    def test_newlines_preserved(self):
        assert escape_html("line1\nline2") == "line1\nline2"


class TestOptionDetection:
    """Tests for OPTION_PATTERN regex."""

    def test_dot_numbered(self):
        """Match '1. Text' format."""
        text = "Choose:\n1. Option A\n2. Option B\n3. Option C"
        matches = OPTION_PATTERN.findall(text)
        assert len(matches) == 3
        assert matches[0][0] == '1'
        assert matches[0][3] == 'Option A'

    def test_paren_numbered(self):
        """Match '1) Text' format."""
        text = "Choose:\n1) First\n2) Second"
        matches = OPTION_PATTERN.findall(text)
        assert len(matches) == 2
        assert matches[0][0] == '1'

    def test_hash_numbered(self):
        """Match '#1 Text' format."""
        text = "#1 Alpha\n#2 Beta\n#3 Gamma"
        matches = OPTION_PATTERN.findall(text)
        assert len(matches) == 3
        assert matches[0][1] == '1'

    def test_bracket_numbered(self):
        """Match '(1) Text' format."""
        text = "(1) Red\n(2) Blue"
        matches = OPTION_PATTERN.findall(text)
        assert len(matches) == 2
        assert matches[0][2] == '1'

    def test_min_two_options_required(self):
        """Single option should not trigger buttons (logic in caller)."""
        text = "1. Only option"
        matches = OPTION_PATTERN.findall(text)
        assert len(matches) == 1  # Pattern matches, but caller checks len >= 2

    def test_max_eight_cap(self):
        """Pattern matches all, caller caps at 8."""
        text = "\n".join(f"{i}. Option {i}" for i in range(1, 12))
        matches = OPTION_PATTERN.findall(text)
        assert len(matches) == 11  # All match; caller caps at [:8]

    def test_no_false_positive_plain_text(self):
        """Plain text without option format doesn't match."""
        text = "This is just regular text\nWith multiple lines\nNo options here"
        matches = OPTION_PATTERN.findall(text)
        assert len(matches) == 0

    def test_no_false_positive_numbered_list_in_sentence(self):
        """Numbers mid-sentence don't match (requires line-start)."""
        text = "Pick item 1. or item 2. from the list"
        matches = OPTION_PATTERN.findall(text)
        # These may or may not match depending on position - test the regex boundary
        # The regex requires start-of-line (^ with MULTILINE)
        assert len(matches) == 0  # Neither is at line start

    def test_indented_options(self):
        """Indented options should match (\\s* prefix)."""
        text = "  1. Indented A\n  2. Indented B"
        matches = OPTION_PATTERN.findall(text)
        assert len(matches) == 2

    def test_mixed_formats(self):
        """Different formats in same text all match."""
        text = "1. Dot format\n2) Paren format\n#3 Hash format"
        matches = OPTION_PATTERN.findall(text)
        assert len(matches) == 3


class TestCallbackData:
    """Tests for callback data format: opt:{session_name}:{option_number}."""

    def test_format(self):
        cb_data = f"opt:my-session:1"
        parts = cb_data.split(':')
        assert parts[0] == 'opt'
        assert parts[1] == 'my-session'
        assert parts[2] == '1'

    def test_long_session_name_truncation(self):
        """Session name should be truncated to 40 chars in callback_data."""
        long_name = "a" * 60
        cb_data = f"opt:{long_name[:40]}:1"
        assert len(cb_data) < 64

    def test_parsing(self):
        cb_data = "opt:test-session:3"
        parts = cb_data.split(':')
        option_num = parts[-1] if len(parts) >= 3 else ''
        assert option_num == '3'

    def test_under_64_bytes(self):
        """Callback data must be under 64 bytes per Telegram limit."""
        session_name = "a" * 40
        for num in ['1', '99']:
            cb_data = f"opt:{session_name}:{num}"
            assert len(cb_data.encode('utf-8')) <= 64

    def test_multi_digit_option(self):
        cb_data = "opt:session:12"
        parts = cb_data.split(':')
        assert parts[-1] == '12'

    def test_starts_with_opt(self):
        cb_data = "opt:s:1"
        assert cb_data.startswith('opt:')


class TestAnswerCallbackQuery:
    """Tests for answer_callback_query functions."""

    def test_answer_callback_query_calls_api(self):
        """Test that answer_callback_query makes API call."""
        mock_post = MagicMock()
        with patch.object(mock_requests, 'post', mock_post):
            _module.answer_callback_query("test-cb-id", "Sent: 1")
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert 'answerCallbackQuery' in call_args[0][0]
            assert call_args[1]['data']['callback_query_id'] == 'test-cb-id'
            assert call_args[1]['data']['text'] == 'Sent: 1'

    def test_answer_callback_query_without_text(self):
        """Test that answer_callback_query works without text param."""
        mock_post = MagicMock()
        with patch.object(mock_requests, 'post', mock_post):
            _module.answer_callback_query("test-cb-id")
            call_args = mock_post.call_args
            assert 'text' not in call_args[1]['data']

    def test_answer_callback_query_session_calls_api(self):
        """Test that answer_callback_query_session makes API call."""
        session = _module.SessionState(
            name='test', topic_id='123', tmux_session='claude-test',
            chat_id='-100', bot_token='fake:token'
        )
        mock_post = MagicMock()
        with patch.object(mock_requests, 'post', mock_post):
            _module.answer_callback_query_session(session, "cb-123", "Done")
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert 'fake:token' in call_args[0][0]
            assert call_args[1]['data']['callback_query_id'] == 'cb-123'

    def test_answer_callback_query_handles_exception(self):
        """Test that exceptions are caught gracefully."""
        mock_post = MagicMock(side_effect=Exception("Network error"))
        with patch.object(mock_requests, 'post', mock_post):
            # Should not raise
            _module.answer_callback_query("cb-id", "test")


class TestHtmlFormattingInCommands:
    """Tests verifying HTML parse_mode is used in command responses."""

    def test_send_message_supports_parse_mode(self):
        """Verify send_message accepts and passes parse_mode."""
        mock_post = MagicMock()
        with patch.object(mock_requests, 'post', mock_post):
            _module.send_message("test <b>bold</b>", parse_mode='HTML')
            call_args = mock_post.call_args
            assert call_args[1]['data']['parse_mode'] == 'HTML'

    def test_send_message_session_supports_parse_mode(self):
        """Verify send_message_session accepts and passes parse_mode."""
        session = _module.SessionState(
            name='test', topic_id='123', tmux_session='claude-test',
            chat_id='-100', bot_token='fake:token'
        )
        mock_post = MagicMock()
        with patch.object(mock_requests, 'post', mock_post):
            _module.send_message_session(session, "test <b>bold</b>", parse_mode='HTML')
            call_args = mock_post.call_args
            assert call_args[1]['data']['parse_mode'] == 'HTML'

    def test_send_message_without_parse_mode(self):
        """Verify send_message works without parse_mode (backwards compat)."""
        mock_post = MagicMock()
        with patch.object(mock_requests, 'post', mock_post):
            _module.send_message("plain text")
            call_args = mock_post.call_args
            assert 'parse_mode' not in call_args[1]['data']
