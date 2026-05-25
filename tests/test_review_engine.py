"""Unit tests for review_engine module."""

import json
import pytest
from unittest.mock import MagicMock, patch

from openai import AuthenticationError

from review_engine import (
    ReviewEngineError,
    _extract_json,
    build_review_prompt,
    get_api_key,
    normalize_review,
    call_openai_api,
)


def _sample_review_json() -> str:
    return json.dumps(
        {
            "summary": "Good",
            "rating": 8,
            "issues": [],
            "bugs": [],
            "security": [],
            "performance": [],
            "optimization": [],
            "readability": [],
            "code_smells": [],
            "time_complexity": "O(n)",
            "complexity_analysis": "Low",
            "optimized_code": "pass",
        }
    )


def test_extract_json_plain():
    data = _extract_json('{"summary": "ok", "rating": 8}')
    assert data["summary"] == "ok"


def test_extract_json_fenced():
    raw = '```json\n{"summary": "x", "rating": 5}\n```'
    data = _extract_json(raw)
    assert data["rating"] == 5


def test_extract_json_invalid_raises():
    with pytest.raises(ReviewEngineError):
        _extract_json("not json at all")


def test_normalize_review_defaults():
    result = normalize_review({"summary": "Hi", "rating": 12})
    assert result["rating"] == 10.0
    assert result["summary"] == "Hi"
    assert isinstance(result["issues"], list)


def test_normalize_review_rating_floor():
    result = normalize_review({"rating": -3})
    assert result["rating"] == 0.0


def test_build_review_prompt_includes_code():
    prompt = build_review_prompt("print(1)", "python", ["Bug Detection"])
    assert "print(1)" in prompt
    assert "Bug Detection" in prompt


def test_get_api_key_from_sidebar():
    with patch.dict("os.environ", {}, clear=True):
        assert get_api_key("test-key") == "test-key"


def test_get_api_key_from_env():
    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-env"}, clear=True):
        assert get_api_key() == "sk-env"


def test_call_openai_empty_code():
    with pytest.raises(ReviewEngineError, match="provide code"):
        call_openai_api("", "python", [], "fake-key")


def test_call_openai_missing_key():
    with pytest.raises(ReviewEngineError, match="API key"):
        call_openai_api("code", "python", [], "")


@patch("review_engine.OpenAI")
def test_call_openai_success(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_message = MagicMock()
    mock_message.content = _sample_review_json()
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    result = call_openai_api("x=1", "python", ["Code Quality"], "test-key")
    assert result["rating"] == 8.0
    assert result["summary"] == "Good"
    mock_client.chat.completions.create.assert_called_once()


@patch("review_engine.OpenAI")
def test_call_openai_invalid_key(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.side_effect = AuthenticationError(
        "Invalid API Key", response=MagicMock(status_code=401), body=None
    )

    with pytest.raises(ReviewEngineError, match="Invalid OpenAI"):
        call_openai_api("code", "python", [], "bad-key")
