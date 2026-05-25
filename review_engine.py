"""
OpenAI API integration for AI-powered code reviews.
Uses the official OpenAI Python SDK and Chat Completions API.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
DEFAULT_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "120"))
MAX_CODE_CHARS = int(os.getenv("OPENAI_MAX_CODE_CHARS", "12000"))
MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "4096"))
MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.getenv("OPENAI_RETRY_DELAY", "2.0"))

REVIEW_CATEGORIES = [
    "Code Quality",
    "Bug Detection",
    "Performance Suggestions",
    "Security Issues",
    "Readability & Best Practices",
    "Complexity Analysis",
]

SYSTEM_PROMPT = """You are an expert automated code reviewer.
Analyze the provided source code thoroughly and return ONLY valid JSON (no markdown fences).
Be specific, actionable, and beginner-friendly in explanations."""

USER_PROMPT_TEMPLATE = """Review the following {language} code.

Selected review categories: {categories}

Source code:
```{language}
{code}
```

Return a JSON object with this exact structure:
{{
  "summary": "2-4 sentence overview of what the code does and overall quality",
  "rating": <number 0-10, one decimal allowed>,
  "time_complexity": "Estimated Big-O time/space complexity with brief explanation",
  "code_smells": [
    {{"name": "smell name", "description": "why it matters", "severity": "Low|Medium|High"}}
  ],
  "issues": [
    {{
      "title": "short issue title",
      "description": "detailed explanation",
      "severity": "Low|Medium|High",
      "category": "one of: Code Quality, Bug Detection, Performance Suggestions, Security Issues, Readability & Best Practices, Complexity Analysis",
      "line": <line number or null>,
      "suggested_fix": "concrete fix steps or code snippet"
    }}
  ],
  "bugs": [
    {{"title": "", "description": "", "severity": "Low|Medium|High", "suggested_fix": ""}}
  ],
  "security": [
    {{"title": "", "description": "", "severity": "Low|Medium|High", "suggested_fix": ""}}
  ],
  "performance": [
    {{"title": "", "description": "", "severity": "Low|Medium|High", "suggested_fix": ""}}
  ],
  "optimization": [
    {{"title": "", "description": "", "severity": "Low|Medium|High", "suggested_fix": ""}}
  ],
  "readability": [
    {{"title": "", "description": "", "severity": "Low|Medium|High", "suggested_fix": ""}}
  ],
  "complexity_analysis": "Paragraph on cyclomatic/cognitive complexity and maintainability",
  "optimized_code": "Full improved version of the code as a string"
}}

Include at least 2-5 issues when problems exist. Use empty arrays only when a section truly has no findings.
Rating should reflect overall quality (10 = excellent production code)."""


class ReviewEngineError(Exception):
    """Base exception for review engine failures."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def get_api_key(sidebar_key: Optional[str] = None) -> str:
    """Resolve API key from sidebar override, environment, or .env."""
    key = (sidebar_key or "").strip()
    if not key:
        key = os.getenv("OPENAI_API_KEY", "").strip()
    return key


def build_review_prompt(code: str, language: str, categories: List[str]) -> str:
    """Build the user prompt sent to OpenAI."""
    cats = ", ".join(categories) if categories else ", ".join(REVIEW_CATEGORIES)
    trimmed = code[:MAX_CODE_CHARS]
    note = ""
    if len(code) > MAX_CODE_CHARS:
        note = (
            f"\n(Note: source was truncated to {MAX_CODE_CHARS} characters "
            "to stay within API limits.)\n"
        )
    return USER_PROMPT_TEMPLATE.format(
        language=language,
        categories=cats,
        code=trimmed + note,
    )


def _extract_json(text: str) -> Dict[str, Any]:
    """Parse JSON from model response, tolerating markdown fences."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError as exc:
                raise ReviewEngineError(
                    "Could not parse AI response as JSON. Try reviewing again."
                ) from exc
        raise ReviewEngineError(
            "Could not parse AI response as JSON. Try reviewing again."
        )


def normalize_review(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure consistent structure with safe defaults."""
    issues = raw.get("issues") or []
    if not isinstance(issues, list):
        issues = []

    def _list(key: str) -> List[Dict[str, Any]]:
        val = raw.get(key) or []
        return val if isinstance(val, list) else []

    rating = raw.get("rating", 0)
    try:
        rating = float(rating)
    except (TypeError, ValueError):
        rating = 0.0
    rating = max(0.0, min(10.0, rating))

    return {
        "summary": str(raw.get("summary") or "No summary provided."),
        "rating": round(rating, 1),
        "time_complexity": str(
            raw.get("time_complexity") or "Unable to estimate complexity."
        ),
        "code_smells": _list("code_smells"),
        "issues": issues,
        "bugs": _list("bugs"),
        "security": _list("security"),
        "performance": _list("performance"),
        "optimization": _list("optimization"),
        "readability": _list("readability"),
        "complexity_analysis": str(
            raw.get("complexity_analysis") or "No complexity analysis provided."
        ),
        "optimized_code": str(raw.get("optimized_code") or ""),
        "raw_response": raw,
    }


def _error_detail(exc: Exception) -> str:
    """Extract readable detail from an OpenAI SDK exception."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error") or {}
        if isinstance(err, dict):
            msg = err.get("message") or err.get("code")
            if msg:
                return str(msg)
    return str(exc)


def _map_openai_error(exc: Exception) -> ReviewEngineError:
    """Convert OpenAI SDK exceptions to ReviewEngineError."""
    if isinstance(exc, AuthenticationError):
        return ReviewEngineError(
            "Invalid OpenAI API key. Check OPENAI_API_KEY in .env or the sidebar. "
            "Create keys at https://platform.openai.com/api-keys",
            status_code=401,
        )
    if isinstance(exc, RateLimitError):
        detail = _error_detail(exc).lower()
        if "insufficient_quota" in detail or "quota" in detail or "billing" in detail:
            return ReviewEngineError(
                "OpenAI quota exceeded — your account has no remaining credits. "
                "Add a payment method and credits at https://platform.openai.com/settings/organization/billing "
                f"Details: {_error_detail(exc)}",
                status_code=429,
            )
        return ReviewEngineError(
            "OpenAI rate limit reached (too many requests or tokens per minute). "
            "Wait 60–90 seconds, avoid clicking Review multiple times, try less code, "
            "or check usage at https://platform.openai.com/usage. "
            f"Details: {_error_detail(exc)}",
            status_code=429,
        )
    if isinstance(exc, APITimeoutError):
        return ReviewEngineError(
            "Request timed out. Try a smaller file or increase OPENAI_TIMEOUT."
        )
    if isinstance(exc, APIConnectionError):
        return ReviewEngineError(f"Could not connect to OpenAI API: {exc}")
    if isinstance(exc, APIStatusError):
        detail = getattr(exc, "message", None) or str(exc)
        code = getattr(exc, "status_code", None)
        if code == 403:
            return ReviewEngineError(
                f"OpenAI API access forbidden: {detail}. "
                "Verify billing and model access at https://platform.openai.com",
                status_code=403,
            )
        return ReviewEngineError(
            f"OpenAI API error ({code}): {detail}",
            status_code=code,
        )
    return ReviewEngineError(f"Unexpected error: {exc}")


def call_openai_api(
    code: str,
    language: str,
    categories: List[str],
    api_key: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Send code to OpenAI Chat Completions API and return normalized review dict.

    Raises:
        ReviewEngineError: On validation, auth, or API errors.
    """
    if not code or not code.strip():
        raise ReviewEngineError("Please provide code to review.")

    if not api_key:
        raise ReviewEngineError(
            "OpenAI API key is missing. Set OPENAI_API_KEY in .env or the sidebar.",
            status_code=401,
        )

    client = OpenAI(api_key=api_key, timeout=timeout)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_review_prompt(code, language, categories),
        },
    ]

    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0.2,
                max_tokens=MAX_OUTPUT_TOKENS,
                response_format={"type": "json_object"},
            )
            break
        except RateLimitError as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BASE_DELAY * (2**attempt))
                continue
            raise _map_openai_error(exc) from exc
        except Exception as exc:
            raise _map_openai_error(exc) from exc
    else:
        raise _map_openai_error(last_exc) if last_exc else ReviewEngineError(
            "OpenAI request failed after retries."
        )

    choices = response.choices or []
    if not choices:
        raise ReviewEngineError("Empty response from OpenAI API.")

    content = choices[0].message.content or ""
    if not content.strip():
        raise ReviewEngineError("OpenAI returned an empty review.")

    parsed = _extract_json(content)
    return normalize_review(parsed)


def run_code_review(
    code: str,
    language: str,
    categories: List[str],
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Public entry point for running a code review."""
    key = get_api_key(api_key)
    return call_openai_api(code, language, categories, key)
