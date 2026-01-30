"""
Unit tests for lib/context_parser.py
Tests line classification, context extraction, and edge cases.
"""

import subprocess
import sys
from pathlib import Path

import pytest

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))
from context_parser import (
    classify_line, extract_notification_context,
    CODE, DIFF, FILE_PATH, PROMPT, OPTION, BULLET, TEXT, EMPTY
)


class TestClassifyLine:
    """Tests for classify_line() line classification."""

    def test_empty_line(self):
        assert classify_line('') == EMPTY

    def test_whitespace_only_line(self):
        assert classify_line('   ') == EMPTY

    def test_prompt_bare(self):
        assert classify_line('> ') == PROMPT

    def test_prompt_with_cursor(self):
        assert classify_line('> _') == PROMPT

    def test_prompt_with_spaces(self):
        assert classify_line('>   ') == PROMPT

    def test_plain_text(self):
        assert classify_line('All 12 tests pass.') == TEXT

    def test_question_text(self):
        assert classify_line('Which approach for the rate limiter?') == TEXT

    def test_sentence_with_colon(self):
        assert classify_line('The implementation includes:') == TEXT

    def test_code_indented_with_brackets(self):
        assert classify_line('    const x = 5;') == CODE

    def test_code_indented_with_function_keyword(self):
        assert classify_line('  function authenticate(req) {') == CODE

    def test_code_indented_with_return(self):
        assert classify_line('    return res.status(401);') == CODE

    def test_code_indented_with_import(self):
        assert classify_line('  import os') == CODE

    def test_code_indented_with_arrow(self):
        assert classify_line('  const f = () => {') == CODE

    def test_indented_text_without_code_signals(self):
        """Indented text without code signals should be TEXT, not CODE."""
        assert classify_line('  JWT token validation') == TEXT

    def test_indented_text_all_tests_passed(self):
        assert classify_line('  All tests passed') == TEXT

    def test_bullet_dash(self):
        assert classify_line('- JWT validation') == BULLET

    def test_bullet_asterisk(self):
        assert classify_line('* Session management') == BULLET

    def test_bullet_indented_one_space(self):
        assert classify_line(' - Rate limiting') == BULLET

    def test_option_dot(self):
        assert classify_line('1. Token bucket') == OPTION

    def test_option_paren(self):
        assert classify_line('2) Sliding window') == OPTION

    def test_option_hash(self):
        assert classify_line('#3 Fixed window') == OPTION

    def test_option_bracket(self):
        assert classify_line('(1) First option') == OPTION

    def test_option_with_ascii_cursor(self):
        """ASCII > cursor prefix (selected option)."""
        assert classify_line('> 1. Yes (Recommended)') == OPTION

    def test_option_with_unicode_cursor_heavy_angle(self):
        """Unicode ❯ (U+276F) cursor prefix used by some CLI tools."""
        assert classify_line('\u276f 1. Yes (Recommended)') == OPTION

    def test_option_with_unicode_cursor_angle_quote(self):
        """Unicode › (U+203A) cursor prefix."""
        assert classify_line('\u203a 1. Yes (Recommended)') == OPTION

    def test_diff_plus(self):
        assert classify_line('+added line') == DIFF

    def test_diff_minus(self):
        assert classify_line('-removed line') == DIFF

    def test_diff_hunk(self):
        assert classify_line('@@ -1,3 +1,4 @@') == DIFF

    def test_diff_git(self):
        assert classify_line('diff --git a/file b/file') == DIFF

    def test_file_path_dash(self):
        assert classify_line('src/app.js - Added auth middleware') == FILE_PATH

    def test_file_path_parens(self):
        assert classify_line('src/routes/login.js (New)') == FILE_PATH

    def test_file_path_em_dash(self):
        assert classify_line('tests/auth.test.js \u2014 12 test cases') == FILE_PATH

    def test_not_file_path_plain(self):
        """Plain text mentioning a path without separator should be TEXT."""
        assert classify_line('Updated the auth module') == TEXT


class TestExtractNotificationContext:
    """Tests for extract_notification_context() main extraction."""

    def test_full_example(self):
        """The canonical example from the requirements."""
        text = (
            "I've made the following changes:\n"
            "\n"
            "  src/app.js - Added auth middleware\n"
            "  src/routes/login.js - New endpoint\n"
            "\n"
            "  function authenticate(req, res, next) {\n"
            "    const token = req.headers.authorization;\n"
            "    if (!token) return res.status(401);\n"
            "  }\n"
            "\n"
            "All 12 tests pass. The implementation includes:\n"
            "- JWT token validation\n"
            "- Session management\n"
            "\n"
            "Which approach for the rate limiter?\n"
            "1. Token bucket\n"
            "2. Sliding window\n"
            "3. Fixed window\n"
            "\n"
            "> _"
        )
        result = extract_notification_context(text)
        assert 'All 12 tests pass' in result
        assert 'JWT token validation' in result
        assert 'Session management' in result
        assert 'Which approach' in result
        assert '1. Token bucket' in result
        assert '2. Sliding window' in result
        assert '3. Fixed window' in result
        # Noise should be omitted
        assert 'function authenticate' not in result
        assert 'src/app.js' not in result
        assert '> _' not in result

    def test_question_only(self):
        text = "What would you like to do next?\n> _"
        result = extract_notification_context(text)
        assert 'What would you like to do next?' in result
        assert '>' not in result

    def test_options_preserved(self):
        text = "Choose:\n1. Option A\n2. Option B\n3. Option C\n> "
        result = extract_notification_context(text)
        assert '1. Option A' in result
        assert '2. Option B' in result
        assert '3. Option C' in result

    def test_options_with_unicode_cursor(self):
        """Option with ❯ cursor prefix should still be extracted."""
        text = "Choose:\n\u276f 1. Option A\n  2. Option B\n  3. Option C\n> "
        result = extract_notification_context(text)
        assert '1. Option A' in result
        assert '2. Option B' in result
        assert '3. Option C' in result

    def test_bullets_preserved(self):
        text = "Changes made:\n- Added tests\n- Fixed bug\n- Updated docs\n> "
        result = extract_notification_context(text)
        assert '- Added tests' in result
        assert '- Fixed bug' in result
        assert '- Updated docs' in result

    def test_code_omitted(self):
        text = (
            "  const x = 5;\n"
            "  function foo() {\n"
            "    return x;\n"
            "  }\n"
            "\n"
            "Does this look correct?\n"
            "> "
        )
        result = extract_notification_context(text)
        assert 'Does this look correct?' in result
        assert 'const x' not in result
        assert 'function foo' not in result

    def test_diffs_omitted(self):
        text = (
            "+added line\n"
            "-removed line\n"
            "@@ -1,3 +1,4 @@\n"
            "\n"
            "Should I apply these changes?\n"
            "> "
        )
        result = extract_notification_context(text)
        assert 'Should I apply' in result
        assert '+added line' not in result

    def test_file_paths_omitted(self):
        text = (
            "src/app.js - Modified\n"
            "src/test.js - Added\n"
            "\n"
            "Ready to deploy?\n"
            "> "
        )
        result = extract_notification_context(text)
        assert 'Ready to deploy?' in result
        assert 'src/app.js' not in result

    def test_prompt_stripped(self):
        text = "Hello world\n> _"
        result = extract_notification_context(text)
        assert '>' not in result
        assert '_' not in result

    def test_intro_text_before_code_omitted(self):
        """Text ending with ':' that introduces a code/filepath block is skipped."""
        text = (
            "I've made the following changes:\n"
            "src/app.js - Added auth\n"
            "\n"
            "All tests pass.\n"
            "> "
        )
        result = extract_notification_context(text)
        assert 'All tests pass' in result
        assert "I've made the following changes" not in result

    def test_max_chars_respected(self):
        text = "A" * 1000 + "\n> "
        result = extract_notification_context(text, max_chars=100)
        assert len(result) <= 100

    def test_fallback_on_all_code(self):
        """If input is entirely code, return truncated input."""
        text = (
            "  const a = 1;\n"
            "  const b = 2;\n"
            "  function foo() {\n"
            "    return a + b;\n"
            "  }\n"
        )
        result = extract_notification_context(text)
        # Should return something (fallback), not empty
        assert len(result) > 0

    def test_fallback_on_empty(self):
        assert extract_notification_context('') == ''
        assert extract_notification_context('   ') == ''

    def test_preserves_line_order(self):
        text = "First line\nSecond line\nThird line\n> "
        result = extract_notification_context(text)
        lines = result.strip().split('\n')
        assert lines[0] == 'First line'
        assert lines[1] == 'Second line'
        assert lines[2] == 'Third line'

    def test_mixed_content_extracts_tail(self):
        """Code at top, NL text at bottom — only tail extracted."""
        text = (
            "  if (err) {\n"
            "    throw err;\n"
            "  }\n"
            "\n"
            "Done. Want to continue?\n"
            "> "
        )
        result = extract_notification_context(text)
        assert 'Done. Want to continue?' in result
        assert 'throw err' not in result


class TestEdgeCases:
    """Edge case tests."""

    def test_only_prompt_line(self):
        result = extract_notification_context('> _')
        # Should return something or empty, but not crash
        assert isinstance(result, str)

    def test_unicode_preserved(self):
        text = "🔔 Alert fired\n✅ Tests passed\n> "
        result = extract_notification_context(text)
        assert '🔔 Alert fired' in result
        assert '✅ Tests passed' in result

    def test_very_long_text(self):
        lines = [f"Line {i}: some text here" for i in range(200)]
        text = '\n'.join(lines) + '\n> '
        result = extract_notification_context(text, max_chars=500)
        assert len(result) <= 500

    def test_no_trailing_newlines(self):
        text = "Simple message\n> "
        result = extract_notification_context(text)
        assert not result.endswith('\n')

    def test_html_not_escaped(self):
        """Parser should NOT escape HTML — that's the caller's job."""
        text = "Use <b>bold</b> & stuff\n> "
        result = extract_notification_context(text)
        assert '<b>' in result
        assert '&' in result

    def test_cli_main_entry(self):
        """Test the __main__ CLI entry point."""
        parser_path = Path(__file__).parent.parent / 'lib' / 'context_parser.py'
        result = subprocess.run(
            [sys.executable, str(parser_path), "Hello world\n> _"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0
        assert 'Hello world' in result.stdout
        assert '>' not in result.stdout

    def test_consecutive_empty_lines_collapsed(self):
        text = "First\n\n\n\nSecond\n> "
        result = extract_notification_context(text)
        # Should not have more than one consecutive blank line
        assert '\n\n\n' not in result

    def test_trailing_terminal_status_bar_stripped(self):
        """Terminal UI lines with []() at the bottom should be skipped."""
        text = (
            "Some old text\n"
            "Want to continue?\n"
            "  ➜  my-repo git:(main) [Opus 4.5] [37%]\n"
            "  ⏵⏵ accept edits (shift+Tab)\n"
            "> _"
        )
        result = extract_notification_context(text)
        assert 'Want to continue?' in result
        assert 'Opus 4.5' not in result
        assert 'accept edits' not in result

    def test_fallback_returns_bottom_not_top(self):
        """When fallback triggers, it should return bottom content."""
        # All code lines — trailing noise stripping empties classified,
        # so fallback returns truncated input from the bottom
        lines = [f"  const x{i} = {i};" for i in range(30)]
        text = '\n'.join(lines)
        result = extract_notification_context(text, max_chars=200)
        # Should contain the last lines, not the first
        assert 'x29' in result
        assert 'x0' not in result
