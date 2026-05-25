"""Unit tests for utils module."""

import pytest

from utils import (
    DEMO_CODE,
    build_txt_report,
    count_by_severity,
    detect_language_from_filename,
    validate_upload,
    issues_to_dataframe,
    merge_issue_lists,
    guess_language_from_code,
)

def test_detect_language_python():
    assert detect_language_from_filename("app.py") == "python"


def test_detect_language_javascript():
    assert detect_language_from_filename("bundle.js") == "javascript"


def test_validate_upload_supported():
    ok, msg = validate_upload("main.cpp")
    assert ok is True
    assert msg == ""


def test_validate_upload_unsupported():
    ok, msg = validate_upload("readme.md")
    assert ok is False
    assert "Unsupported" in msg


def test_count_by_severity():
    items = [
        {"severity": "High"},
        {"severity": "low"},
        {"severity": "Medium"},
    ]
    counts = count_by_severity(items)
    assert counts["High"] == 1
    assert counts["Low"] == 1
    assert counts["Medium"] == 1


def test_issues_to_dataframe_empty():
    df = issues_to_dataframe([])
    assert len(df) == 0


def test_issues_to_dataframe_rows():
    df = issues_to_dataframe(
        [{"title": "Bug", "severity": "High", "description": "x", "suggested_fix": "y"}]
    )
    assert len(df) == 1
    assert df.iloc[0]["Title"] == "Bug"


def test_merge_issue_lists():
    review = {
        "issues": [{"title": "A"}],
        "bugs": [{"title": "B"}],
        "security": [],
    }
    merged = merge_issue_lists(review)
    assert len(merged) == 2


def test_build_txt_report_contains_summary():
    review = {
        "summary": "Test summary",
        "rating": 7.5,
        "time_complexity": "O(n)",
        "complexity_analysis": "Simple",
        "issues": [],
        "bugs": [],
        "security": [],
        "performance": [],
        "code_smells": [],
        "optimized_code": "",
    }
    txt = build_txt_report(review, DEMO_CODE, "python")
    assert "Test summary" in txt
    assert "7.5" in txt


def test_guess_language_python():
    assert guess_language_from_code("def foo(): pass") == "python"


def test_demo_code_not_empty():
    assert "fibonacci" in DEMO_CODE
