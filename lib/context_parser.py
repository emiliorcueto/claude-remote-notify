"""
Notification context parser - extracts natural language from terminal output.

Operates on the output of format_for_telegram() (ANSI-stripped, tables converted).
Classifies each line, then extracts only natural language content (questions,
summaries, options, bullets) working backwards from the end of the output.

Line Classification:

  Type       Pattern                                      Example
  --------   -----------------------------------------    ---------------------
  CODE       2+ leading spaces AND code signals            const x = 5;
  DIFF       Starts with +/-/@@/diff --git                 +added line
  FILE_PATH  Path with extension + separator (- or ()      src/app.js - Added auth
  PROMPT     Matches > or > _ at line start                > _
  OPTION     Numbered: 1. / 1) / #1 / (1)                 1. Token bucket
  BULLET     Starts with - or * at column 0                - JWT validation
  TEXT       Everything else (natural language)             All 12 tests pass.
  EMPTY      Blank line

Code signals: {}[]();  keywords (import, def, class, function, const, let,
var, return, if, else, for, while)  operators (=>, ->, &&, ||)
"""

import re
import sys

# Line type constants
CODE = 'code'
DIFF = 'diff'
FILE_PATH = 'filepath'
PROMPT = 'prompt'
OPTION = 'option'
BULLET = 'bullet'
TEXT = 'text'
EMPTY = 'empty'

# Natural language types (kept in output)
NL_TYPES = {TEXT, BULLET, OPTION}

# Code signal patterns
CODE_SIGNALS = re.compile(
    r'[{}\[\]();]|'
    r'\b(import|from|def|class|function|const|let|var|return|if|else|for|while)\b|'
    r'=>|->|::|&&|\|\|'
)

# File path pattern: word/word.ext - description  OR  word/word.ext (Modified|Added|etc)
FILE_PATH_PATTERN = re.compile(
    r'^\s*\S+/\S+\.\w+\s*[-\u2014(]'
)

# Diff line pattern
# +text or -text (no space after +/-) = diff content
# +++ or --- = diff header
# @@ = diff hunk
# Note: "- text" (dash space) is a BULLET, not a diff — handled by checking BULLET first
DIFF_PATTERN = re.compile(r'^[+][^\s]|^[-][^\s]|^[+]{2,3}\s|^[-]{2,3}\s|^@@\s|^diff --git')

# Prompt line pattern (Claude Code's > prompt)
PROMPT_PATTERN = re.compile(r'^>\s*[_\s]*$')

# Option pattern (numbered items)
OPTION_PATTERN = re.compile(
    r'^\s*(?:(\d+)[.\)]\s+|#(\d+)\s+|\((\d+)\)\s+)(.+)$'
)


def classify_line(line: str) -> str:
    """Classify a single line of terminal output."""
    stripped = line.rstrip()

    if not stripped:
        return EMPTY

    if PROMPT_PATTERN.match(stripped):
        return PROMPT

    if OPTION_PATTERN.match(stripped):
        return OPTION

    # Check BULLET before DIFF (both can start with -)
    # "- text" (dash space) = bullet, "-text" (dash non-space) = diff
    if re.match(r'^\s{0,1}[-*]\s', stripped):
        return BULLET

    if DIFF_PATTERN.match(stripped):
        return DIFF

    if FILE_PATH_PATTERN.match(stripped):
        return FILE_PATH

    leading_spaces = len(stripped) - len(stripped.lstrip())
    if leading_spaces >= 2 and CODE_SIGNALS.search(stripped):
        return CODE

    return TEXT


def extract_notification_context(text: str, max_chars: int = 500) -> str:
    """Extract natural language context from formatted terminal output.

    Takes the output of format_for_telegram() and returns only the natural
    language portions: questions, summaries, options, and bullet lists.
    Code blocks, diffs, file paths, and prompt lines are omitted.

    Works backwards from the end of the text (most recent = most relevant).
    Falls back to truncated full text if parsing yields too little content.

    Args:
        text: Formatted terminal output (ANSI already stripped).
        max_chars: Maximum output length. Default 500.

    Returns:
        Extracted natural language text, or truncated input as fallback.
    """
    if not text or not text.strip():
        return ''

    lines = text.split('\n')

    # Classify each line
    classified = [(line, classify_line(line)) for line in lines]

    # Strip trailing PROMPT and EMPTY lines
    while classified and classified[-1][1] in (PROMPT, EMPTY):
        classified.pop()

    # Strip trailing noise (terminal UI, status bar lines with []() chars)
    # These aren't real code — just terminal chrome that contains code signals.
    while classified and classified[-1][1] in (CODE, DIFF, FILE_PATH, EMPTY):
        classified.pop()

    if not classified:
        # Return bottom portion of text (most recent = most relevant)
        stripped = text.strip()
        if len(stripped) <= max_chars:
            return stripped
        # Collect whole lines from the bottom
        all_lines = stripped.split('\n')
        tail = []
        total = 0
        for line in reversed(all_lines):
            line_len = len(line) + 1
            if total + line_len > max_chars:
                break
            tail.append(line)
            total += line_len
        tail.reverse()
        return '\n'.join(tail).strip()

    # Work backwards: collect NL lines, stop at code/diff/filepath block
    collected = []
    total_chars = 0
    hit_noise = False

    for line, line_type in reversed(classified):
        if line_type in (CODE, DIFF, FILE_PATH):
            hit_noise = True
            break
        if line_type == EMPTY:
            # Keep blank lines between NL blocks for readability
            if collected:
                collected.append(line)
            continue
        if line_type in NL_TYPES:
            line_len = len(line) + 1  # +1 for newline
            if total_chars + line_len > max_chars:
                break
            collected.append(line)
            total_chars += line_len

    # If we hit noise, check if the line just before the noise block is
    # "intro text" (e.g. "I've made the following changes:") and remove it
    if hit_noise and collected:
        last_collected = collected[-1].strip()
        if last_collected.endswith(':'):
            collected.pop()

    # Reverse to restore original order
    collected.reverse()

    # Strip leading/trailing empty lines from collected
    while collected and not collected[0].strip():
        collected.pop(0)
    while collected and not collected[-1].strip():
        collected.pop()

    # Collapse consecutive empty lines
    collapsed = []
    prev_empty = False
    for line in collected:
        is_empty = not line.strip()
        if is_empty and prev_empty:
            continue
        collapsed.append(line)
        prev_empty = is_empty

    result = '\n'.join(collapsed).strip()

    # Fallback: if too little was extracted, return bottom of full text
    if len(result) < 10:
        fallback_lines = [line for line, lt in classified if lt != PROMPT]
        # Collect from bottom (most recent = most relevant)
        fb_collected = []
        fb_total = 0
        for line in reversed(fallback_lines):
            line_len = len(line) + 1
            if fb_total + line_len > max_chars:
                break
            fb_collected.append(line)
            fb_total += line_len
        fb_collected.reverse()
        return '\n'.join(fb_collected).strip()

    return result


if __name__ == '__main__':
    input_text = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    max_c = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    result = extract_notification_context(input_text, max_chars=max_c)
    print(result)
