# tests/test_gemini.py
"""Tests for Gemini API client retry logic."""

from unittest.mock import MagicMock, patch

import pytest

from src.extraction.gemini import _call_gemini, _MAX_RETRIES


def test_call_gemini_returns_on_success():
    """Successful call returns the response directly."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = "response"

    result = _call_gemini(mock_client, model="test", contents="hello")

    assert result == "response"
    assert mock_client.models.generate_content.call_count == 1


def test_call_gemini_retries_on_429():
    """429 errors trigger a retry after waiting."""
    from google.genai.errors import ClientError

    mock_client = MagicMock()
    error = ClientError.__new__(ClientError)
    error.code = 429
    error.message = "rate limited"
    mock_client.models.generate_content.side_effect = [error, "success"]

    with patch("src.extraction.gemini.time.sleep") as mock_sleep:
        result = _call_gemini(mock_client, model="test", contents="hello")

    assert result == "success"
    assert mock_client.models.generate_content.call_count == 2
    mock_sleep.assert_called_once_with(60)


def test_call_gemini_raises_after_max_retries():
    """After _MAX_RETRIES 429 errors, the exception is raised."""
    from google.genai.errors import ClientError

    mock_client = MagicMock()
    error = ClientError.__new__(ClientError)
    error.code = 429
    error.message = "rate limited"
    mock_client.models.generate_content.side_effect = [error] * _MAX_RETRIES

    with patch("src.extraction.gemini.time.sleep"):
        with pytest.raises(ClientError):
            _call_gemini(mock_client, model="test", contents="hello")

    assert mock_client.models.generate_content.call_count == _MAX_RETRIES


def test_call_gemini_raises_non_429_immediately():
    """Non-429 errors are raised without retry."""
    from google.genai.errors import ClientError

    mock_client = MagicMock()
    error = ClientError.__new__(ClientError)
    error.code = 400
    error.message = "bad request"
    mock_client.models.generate_content.side_effect = error

    with pytest.raises(ClientError):
        _call_gemini(mock_client, model="test", contents="hello")

    assert mock_client.models.generate_content.call_count == 1
