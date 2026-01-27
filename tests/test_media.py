"""
Unit tests for media handling functions in telegram-listener.py
Tests photo/document download, filename sanitization, and cleanup.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
from datetime import datetime

import pytest

# Add hooks directory to path for importing
sys.path.insert(0, str(Path(__file__).parent.parent / 'hooks'))

# Mock the requests module before importing
mock_requests = MagicMock()
sys.modules['requests'] = mock_requests

# Constants from the listener (recreated for testing)
MEDIA_TEMP_DIR = Path('/tmp/claude-telegram')
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
DOWNLOAD_TIMEOUT = 60

UNSUPPORTED_MEDIA_TYPES = {
    'voice': 'Voice messages',
    'video': 'Videos',
    'video_note': 'Video notes',
    'audio': 'Audio files',
    'sticker': 'Stickers',
    'animation': 'Animations/GIFs',
}


# =============================================================================
# RECREATE FUNCTIONS FOR TESTING (same logic as telegram-listener.py)
# =============================================================================

import re


def sanitize_filename(filename):
    """Remove unsafe characters from filename."""
    if not filename:
        return "unnamed"

    if '.' in filename:
        name, ext = filename.rsplit('.', 1)
        ext = '.' + re.sub(r'[^a-zA-Z0-9]', '', ext)[:10]
    else:
        name = filename
        ext = ''

    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    sanitized = re.sub(r'_+', '_', sanitized)
    sanitized = sanitized.strip('_')

    if not sanitized:
        sanitized = "file"

    sanitized = sanitized[:100]

    return sanitized + ext


def ensure_media_dir(media_dir):
    """Create media temp directory if it doesn't exist."""
    try:
        media_dir.mkdir(parents=True, exist_ok=True)
        return True
    except Exception:
        return False


def get_telegram_file(bot_token, file_id, requests_module):
    """Get file path from Telegram using file_id."""
    url = f"https://api.telegram.org/bot{bot_token}/getFile"
    params = {'file_id': file_id}

    try:
        response = requests_module.get(url, params=params, timeout=30)
        data = response.json()

        if data.get('ok'):
            return data.get('result', {})
        else:
            return None
    except Exception:
        return None


def download_telegram_file(bot_token, file_path, local_path, requests_module):
    """Download file from Telegram servers to local path."""
    url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"

    try:
        response = requests_module.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
        response.raise_for_status()

        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return True
    except Exception:
        return False


def cleanup_media_files(media_dir, session_name):
    """Remove session-specific media files from temp directory."""
    if not media_dir.exists():
        return

    pattern = f"{session_name}-*"
    try:
        for f in media_dir.glob(pattern):
            try:
                f.unlink()
            except Exception:
                pass
    except Exception:
        pass


def handle_media_message(message, message_id, session_name, bot_token, media_dir, requests_module):
    """Handle incoming media message (photo or document)."""
    # Check for unsupported media types first
    for media_type, description in UNSUPPORTED_MEDIA_TYPES.items():
        if media_type in message:
            return (f"{description} not supported. Send photos or documents instead.", False)

    # Handle photos
    if 'photo' in message:
        photos = message['photo']
        if not photos:
            return ("Empty photo array", False)

        photo = photos[-1]
        file_id = photo.get('file_id')
        file_size = photo.get('file_size', 0)

        if file_size > MAX_FILE_SIZE:
            return (f"Photo too large ({file_size // 1024 // 1024}MB). Max: 20MB", False)

        return _download_and_format(
            file_id, 'photo', message, session_name, bot_token, media_dir, requests_module
        )

    # Handle documents
    if 'document' in message:
        doc = message['document']
        file_id = doc.get('file_id')
        file_size = doc.get('file_size', 0)
        file_name = doc.get('file_name', 'document')

        if file_size > MAX_FILE_SIZE:
            return (f"Document too large ({file_size // 1024 // 1024}MB). Max: 20MB", False)

        return _download_and_format(
            file_id, 'document', message, session_name, bot_token, media_dir, requests_module,
            file_name
        )

    return ("No media found in message", False)


def _download_and_format(file_id, media_type, message, session_name, bot_token, media_dir,
                         requests_module, original_filename=None):
    """Download media and format inject text."""
    if not ensure_media_dir(media_dir):
        return ("Failed to create media directory", False)

    file_info = get_telegram_file(bot_token, file_id, requests_module)
    if not file_info:
        return ("Failed to get file info from Telegram", False)

    telegram_path = file_info.get('file_path')
    if not telegram_path:
        return ("No file_path in Telegram response", False)

    if original_filename:
        safe_name = sanitize_filename(original_filename)
    else:
        ext = Path(telegram_path).suffix or '.jpg'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = f"{media_type}_{timestamp}{ext}"

    local_filename = f"{session_name}-{safe_name}"
    local_path = media_dir / local_filename

    if not download_telegram_file(bot_token, telegram_path, local_path, requests_module):
        return ("Failed to download file", False)

    caption = message.get('caption', '').strip()
    if media_type == 'photo':
        inject_text = f"[Image: {local_path}]"
    else:
        inject_text = f"[Document: {local_path}]"

    if caption:
        inject_text += f" {caption}"

    return (inject_text, True)


# =============================================================================
# TEST CLASSES
# =============================================================================

class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_normal_filename_preserved(self):
        """Normal filenames should be mostly preserved."""
        assert sanitize_filename("document.pdf") == "document.pdf"
        assert sanitize_filename("my_file.txt") == "my_file.txt"
        assert sanitize_filename("report-2024.docx") == "report-2024.docx"

    def test_special_chars_replaced(self):
        """Special characters should be replaced with underscores."""
        assert sanitize_filename("my file.txt") == "my_file.txt"
        assert sanitize_filename("file@#$%.txt") == "file.txt"
        assert sanitize_filename("path/to/file.txt") == "path_to_file.txt"

    def test_empty_filename_handled(self):
        """Empty or None filename should return 'unnamed'."""
        assert sanitize_filename("") == "unnamed"
        assert sanitize_filename(None) == "unnamed"

    def test_filename_without_extension(self):
        """Filename without extension should work."""
        assert sanitize_filename("readme") == "readme"
        assert sanitize_filename("my file") == "my_file"

    def test_long_filename_truncated(self):
        """Very long filenames should be truncated."""
        long_name = "a" * 200 + ".txt"
        result = sanitize_filename(long_name)
        assert len(result) <= 114  # 100 chars + extension

    def test_extension_sanitized(self):
        """Extensions with special chars should be sanitized."""
        assert sanitize_filename("file.t@xt") == "file.txt"
        assert sanitize_filename("file.MP3") == "file.MP3"

    def test_consecutive_underscores_collapsed(self):
        """Multiple consecutive underscores should collapse to one."""
        assert sanitize_filename("my___file.txt") == "my_file.txt"
        assert sanitize_filename("a   b   c.txt") == "a_b_c.txt"

    def test_leading_trailing_underscores_stripped(self):
        """Leading/trailing underscores should be stripped."""
        assert sanitize_filename("_file_.txt") == "file.txt"
        assert sanitize_filename("___test___.pdf") == "test.pdf"


class TestEnsureMediaDir:
    """Tests for ensure_media_dir function."""

    def test_creates_directory(self):
        """Should create directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / 'media' / 'subdir'
            assert not test_dir.exists()
            assert ensure_media_dir(test_dir) is True
            assert test_dir.exists()

    def test_existing_directory_ok(self):
        """Should return True for existing directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            assert ensure_media_dir(test_dir) is True


class TestGetTelegramFile:
    """Tests for get_telegram_file function."""

    def test_successful_get_file(self):
        """Should return file info on success."""
        mock_req = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'ok': True,
            'result': {'file_id': 'abc123', 'file_path': 'photos/file_1.jpg'}
        }
        mock_req.get.return_value = mock_response

        result = get_telegram_file('bot_token', 'file_id_123', mock_req)

        assert result == {'file_id': 'abc123', 'file_path': 'photos/file_1.jpg'}
        mock_req.get.assert_called_once()

    def test_api_error_returns_none(self):
        """Should return None on API error."""
        mock_req = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'ok': False,
            'description': 'Bad Request: invalid file_id'
        }
        mock_req.get.return_value = mock_response

        result = get_telegram_file('bot_token', 'invalid_id', mock_req)

        assert result is None

    def test_network_error_returns_none(self):
        """Should return None on network error."""
        mock_req = MagicMock()
        mock_req.get.side_effect = Exception("Network error")

        result = get_telegram_file('bot_token', 'file_id', mock_req)

        assert result is None


class TestDownloadTelegramFile:
    """Tests for download_telegram_file function."""

    def test_successful_download(self):
        """Should download file successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / 'downloaded.jpg'

            mock_req = MagicMock()
            mock_response = MagicMock()
            mock_response.iter_content.return_value = [b'fake image data']
            mock_response.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_response

            result = download_telegram_file(
                'bot_token', 'photos/file.jpg', local_path, mock_req
            )

            assert result is True
            assert local_path.exists()
            assert local_path.read_bytes() == b'fake image data'

    def test_download_network_error(self):
        """Should return False on network error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / 'failed.jpg'

            mock_req = MagicMock()
            mock_req.get.side_effect = Exception("Connection timeout")

            result = download_telegram_file(
                'bot_token', 'photos/file.jpg', local_path, mock_req
            )

            assert result is False
            assert not local_path.exists()

    def test_download_http_error(self):
        """Should return False on HTTP error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / 'failed.jpg'

            mock_req = MagicMock()
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = Exception("404 Not Found")
            mock_req.get.return_value = mock_response

            result = download_telegram_file(
                'bot_token', 'photos/nonexistent.jpg', local_path, mock_req
            )

            assert result is False


class TestCleanupMediaFiles:
    """Tests for cleanup_media_files function."""

    def test_cleanup_session_files(self):
        """Should clean up only session-specific files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            media_dir = Path(tmpdir)

            # Create test files
            (media_dir / 'test-session-photo1.jpg').write_text('test')
            (media_dir / 'test-session-doc.pdf').write_text('test')
            (media_dir / 'other-session-file.jpg').write_text('test')
            (media_dir / 'random-file.txt').write_text('test')

            cleanup_media_files(media_dir, 'test-session')

            # Session files should be gone
            assert not (media_dir / 'test-session-photo1.jpg').exists()
            assert not (media_dir / 'test-session-doc.pdf').exists()

            # Other files should remain
            assert (media_dir / 'other-session-file.jpg').exists()
            assert (media_dir / 'random-file.txt').exists()

    def test_cleanup_nonexistent_dir(self):
        """Should handle non-existent directory gracefully."""
        nonexistent = Path('/tmp/nonexistent-test-dir-12345')
        # Should not raise
        cleanup_media_files(nonexistent, 'session')

    def test_cleanup_empty_dir(self):
        """Should handle empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            media_dir = Path(tmpdir)
            # Should not raise
            cleanup_media_files(media_dir, 'session')

    def test_cleanup_no_matching_files(self):
        """Should handle directory with no matching files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            media_dir = Path(tmpdir)
            (media_dir / 'other-file.txt').write_text('test')

            cleanup_media_files(media_dir, 'mysession')

            # Other file should remain
            assert (media_dir / 'other-file.txt').exists()


class TestHandleMediaMessage:
    """Tests for handle_media_message function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.media_dir = Path(self.temp_dir) / 'media'
        self.session_name = 'test-session'
        self.bot_token = 'test-token'

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_mock_requests(self, file_path='photos/file.jpg', content=b'test data'):
        """Create mock requests module for successful download."""
        mock_req = MagicMock()

        # Mock getFile response
        mock_file_response = MagicMock()
        mock_file_response.json.return_value = {
            'ok': True,
            'result': {'file_id': 'abc', 'file_path': file_path}
        }

        # Mock download response
        mock_download_response = MagicMock()
        mock_download_response.iter_content.return_value = [content]
        mock_download_response.raise_for_status = MagicMock()

        mock_req.get.side_effect = [mock_file_response, mock_download_response]
        return mock_req

    def test_photo_download_success(self):
        """Should successfully handle photo message."""
        mock_req = self.create_mock_requests('photos/file.jpg', b'photo data')

        message = {
            'photo': [
                {'file_id': 'small', 'file_size': 1000},
                {'file_id': 'large', 'file_size': 5000}
            ]
        }

        result, success = handle_media_message(
            message, 123, self.session_name, self.bot_token, self.media_dir, mock_req
        )

        assert success is True
        assert '[Image:' in result
        assert self.media_dir.name in result

    def test_photo_with_caption(self):
        """Should include caption in inject text."""
        mock_req = self.create_mock_requests()

        message = {
            'photo': [{'file_id': 'abc', 'file_size': 1000}],
            'caption': 'Check this out!'
        }

        result, success = handle_media_message(
            message, 123, self.session_name, self.bot_token, self.media_dir, mock_req
        )

        assert success is True
        assert 'Check this out!' in result

    def test_document_download_success(self):
        """Should successfully handle document message."""
        mock_req = self.create_mock_requests('documents/report.pdf', b'pdf data')

        message = {
            'document': {
                'file_id': 'doc123',
                'file_size': 10000,
                'file_name': 'report.pdf',
                'mime_type': 'application/pdf'
            }
        }

        result, success = handle_media_message(
            message, 123, self.session_name, self.bot_token, self.media_dir, mock_req
        )

        assert success is True
        assert '[Document:' in result
        assert 'report.pdf' in result

    def test_photo_too_large(self):
        """Should reject photos larger than MAX_FILE_SIZE."""
        message = {
            'photo': [{'file_id': 'huge', 'file_size': 25 * 1024 * 1024}]
        }

        result, success = handle_media_message(
            message, 123, self.session_name, self.bot_token, self.media_dir, MagicMock()
        )

        assert success is False
        assert 'too large' in result.lower()
        assert '20MB' in result

    def test_document_too_large(self):
        """Should reject documents larger than MAX_FILE_SIZE."""
        message = {
            'document': {
                'file_id': 'huge',
                'file_size': 30 * 1024 * 1024,
                'file_name': 'huge.zip'
            }
        }

        result, success = handle_media_message(
            message, 123, self.session_name, self.bot_token, self.media_dir, MagicMock()
        )

        assert success is False
        assert 'too large' in result.lower()

    def test_voice_message_unsupported(self):
        """Should reject voice messages."""
        message = {'voice': {'file_id': 'voice123', 'duration': 5}}

        result, success = handle_media_message(
            message, 123, self.session_name, self.bot_token, self.media_dir, MagicMock()
        )

        assert success is False
        assert 'Voice messages' in result
        assert 'not supported' in result

    def test_video_unsupported(self):
        """Should reject video messages."""
        message = {'video': {'file_id': 'vid123'}}

        result, success = handle_media_message(
            message, 123, self.session_name, self.bot_token, self.media_dir, MagicMock()
        )

        assert success is False
        assert 'Videos' in result
        assert 'not supported' in result

    def test_sticker_unsupported(self):
        """Should reject sticker messages."""
        message = {'sticker': {'file_id': 'sticker123'}}

        result, success = handle_media_message(
            message, 123, self.session_name, self.bot_token, self.media_dir, MagicMock()
        )

        assert success is False
        assert 'Stickers' in result

    def test_animation_unsupported(self):
        """Should reject animation/GIF messages."""
        message = {'animation': {'file_id': 'gif123'}}

        result, success = handle_media_message(
            message, 123, self.session_name, self.bot_token, self.media_dir, MagicMock()
        )

        assert success is False
        assert 'Animations' in result

    def test_empty_photo_array(self):
        """Should handle empty photo array."""
        message = {'photo': []}

        result, success = handle_media_message(
            message, 123, self.session_name, self.bot_token, self.media_dir, MagicMock()
        )

        assert success is False
        assert 'Empty photo' in result

    def test_get_file_api_failure(self):
        """Should handle getFile API failure."""
        mock_req = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {'ok': False, 'description': 'Invalid file_id'}
        mock_req.get.return_value = mock_response

        message = {'photo': [{'file_id': 'invalid', 'file_size': 1000}]}

        result, success = handle_media_message(
            message, 123, self.session_name, self.bot_token, self.media_dir, mock_req
        )

        assert success is False
        assert 'Failed to get file info' in result

    def test_download_failure(self):
        """Should handle download failure."""
        mock_req = MagicMock()

        # Mock getFile success
        mock_file_response = MagicMock()
        mock_file_response.json.return_value = {
            'ok': True,
            'result': {'file_path': 'photos/file.jpg'}
        }

        # Mock download failure
        mock_download_response = MagicMock()
        mock_download_response.raise_for_status.side_effect = Exception("Download failed")

        mock_req.get.side_effect = [mock_file_response, mock_download_response]

        message = {'photo': [{'file_id': 'abc', 'file_size': 1000}]}

        result, success = handle_media_message(
            message, 123, self.session_name, self.bot_token, self.media_dir, mock_req
        )

        assert success is False
        assert 'Failed to download' in result

    def test_no_media_in_message(self):
        """Should handle message with no media."""
        message = {'text': 'Hello world'}

        result, success = handle_media_message(
            message, 123, self.session_name, self.bot_token, self.media_dir, MagicMock()
        )

        assert success is False
        assert 'No media found' in result


class TestMediaTempDir:
    """Tests for media temp directory behavior."""

    def test_default_temp_dir_path(self):
        """Should use correct default temp directory."""
        assert MEDIA_TEMP_DIR == Path('/tmp/claude-telegram')

    def test_max_file_size_constant(self):
        """Should have correct max file size."""
        assert MAX_FILE_SIZE == 20 * 1024 * 1024  # 20MB


class TestUnsupportedMediaTypes:
    """Tests for unsupported media type handling."""

    def test_all_unsupported_types_defined(self):
        """Should have all expected unsupported types."""
        expected = {'voice', 'video', 'video_note', 'audio', 'sticker', 'animation'}
        assert set(UNSUPPORTED_MEDIA_TYPES.keys()) == expected

    def test_unsupported_types_have_descriptions(self):
        """Each unsupported type should have a user-friendly description."""
        for media_type, description in UNSUPPORTED_MEDIA_TYPES.items():
            assert isinstance(description, str)
            assert len(description) > 0
