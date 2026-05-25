"""
Utility helpers: file handling, syntax highlighting, reports, and UI helpers.
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fpdf import FPDF
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer

# Supported upload extensions mapped to Pygments / display language
SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".html": "html",
    ".css": "css",
}

SUPPORTED_LANGUAGES = sorted(set(SUPPORTED_EXTENSIONS.values()))

DEMO_CODE = '''def fibonacci(n):
    """Return the nth Fibonacci number (inefficient demo for review)."""
    if n < 0:
        raise ValueError("n must be non-negative")
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b


def process_users(users):
    password = "admin123"  # hardcoded secret
    results = []
    for i in range(len(users)):
        user = users[i]
        if user["role"] == "admin":
            results.append(user)
    return results


if __name__ == "__main__":
    print(fibonacci(10))
    print(process_users([{"name": "Ada", "role": "admin"}]))
'''

SEVERITY_COLORS = {
    "low": "#22c55e",
    "medium": "#f59e0b",
    "high": "#ef4444",
}

SEVERITY_ICONS = {
    "low": "🟢",
    "medium": "🟡",
    "high": "🔴",
}


def detect_language_from_filename(filename: str) -> Optional[str]:
    """Detect language from file extension."""
    ext = Path(filename).suffix.lower()
    return SUPPORTED_EXTENSIONS.get(ext)


def validate_upload(filename: str) -> Tuple[bool, str]:
    """Return (ok, message) for uploaded file."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS.keys()))
        return False, f"Unsupported file type '{ext}'. Supported: {supported}"
    return True, ""


def read_uploaded_file(uploaded_file) -> Tuple[str, str]:
    """Read Streamlit uploaded file; returns (content, language)."""
    filename = uploaded_file.name
    ok, msg = validate_upload(filename)
    if not ok:
        raise ValueError(msg)
    content = uploaded_file.getvalue().decode("utf-8", errors="replace")
    language = detect_language_from_filename(filename) or "text"
    return content, language


def guess_language_from_code(code: str, hint: str = "python") -> str:
    """Guess Pygments lexer language from code."""
    try:
        lexer = guess_lexer(code)
        name = lexer.name.lower()
        mapping = {
            "python": "python",
            "javascript": "javascript",
            "java": "java",
            "c++": "cpp",
            "c": "c",
            "html": "html",
            "css": "css",
        }
        for key, val in mapping.items():
            if key in name:
                return val
    except Exception:
        pass
    return hint if hint in SUPPORTED_LANGUAGES else "python"


def highlight_code(code: str, language: str = "python") -> str:
    """Return HTML with Pygments syntax highlighting."""
    try:
        lexer = get_lexer_by_name(language, stripall=True)
    except Exception:
        lexer = TextLexer()
    formatter = HtmlFormatter(
        style="monokai",
        noclasses=False,
        cssclass="highlight",
        linenos=True,
    )
    return highlight(code, lexer, formatter) + HtmlFormatter().get_style_defs(
        ".highlight"
    )


def severity_style(severity: str) -> str:
    """CSS color for severity badge."""
    return SEVERITY_COLORS.get((severity or "low").lower(), "#94a3b8")


def severity_icon(severity: str) -> str:
    return SEVERITY_ICONS.get((severity or "low").lower(), "⚪")


def issues_to_dataframe(items: List[Dict[str, Any]]) -> pd.DataFrame:
    """Convert issue list to pandas DataFrame for tables."""
    if not items:
        return pd.DataFrame(
            columns=["Severity", "Title", "Description", "Suggested Fix"]
        )
    rows = []
    for item in items:
        rows.append(
            {
                "Severity": item.get("severity", "Low"),
                "Title": item.get("title", item.get("name", "Issue")),
                "Description": item.get("description", ""),
                "Suggested Fix": item.get("suggested_fix", item.get("fix", "")),
            }
        )
    return pd.DataFrame(rows)


def count_by_severity(items: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count issues grouped by severity."""
    counts = {"Low": 0, "Medium": 0, "High": 0}
    for item in items:
        sev = str(item.get("severity", "Low")).title()
        if sev in counts:
            counts[sev] += 1
    return counts


def build_txt_report(
    review: Dict[str, Any],
    code: str,
    language: str,
    filename: str = "snippet",
) -> str:
    """Build plain-text report for download."""
    lines = [
        "=" * 60,
        "AI CODE REVIEW REPORT",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"File: {filename}",
        f"Language: {language}",
        "=" * 60,
        "",
        "SUMMARY",
        "-" * 40,
        review.get("summary", ""),
        "",
        f"FINAL RATING: {review.get('rating', 0)}/10",
        f"TIME COMPLEXITY: {review.get('time_complexity', 'N/A')}",
        "",
        "COMPLEXITY ANALYSIS",
        "-" * 40,
        review.get("complexity_analysis", ""),
        "",
    ]

    def _section(title: str, items: List[Dict[str, Any]]) -> None:
        lines.append(title)
        lines.append("-" * 40)
        if not items:
            lines.append("  (none)")
        for i, item in enumerate(items, 1):
            lines.append(
                f"  {i}. [{item.get('severity', 'Low')}] "
                f"{item.get('title', item.get('name', 'Item'))}"
            )
            if item.get("description"):
                lines.append(f"     {item['description']}")
            fix = item.get("suggested_fix") or item.get("fix")
            if fix:
                lines.append(f"     Fix: {fix}")
        lines.append("")

    _section("ALL ISSUES", review.get("issues", []))
    _section("BUGS", review.get("bugs", []))
    _section("SECURITY", review.get("security", []))
    _section("PERFORMANCE / OPTIMIZATION", review.get("performance", []))
    _section("CODE SMELLS", review.get("code_smells", []))

    lines.extend(["OPTIMIZED CODE", "-" * 40, review.get("optimized_code", ""), ""])
    lines.extend(["ORIGINAL CODE", "-" * 40, code])
    return "\n".join(lines)


class ReviewPDF(FPDF):
    """Simple PDF report generator."""

    def header(self) -> None:
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, "AI Code Review Report", new_x="LMARGIN", new_y="NEXT", align="C")
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def section_title(self, title: str) -> None:
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text: str) -> None:
        self.set_font("Helvetica", "", 9)
        safe = _pdf_safe(text)
        self.multi_cell(0, 5, safe)
        self.ln(2)


def _pdf_safe(text: str) -> str:
    """Replace characters unsupported by core PDF fonts."""
    return (
        text.replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .encode("latin-1", errors="replace")
        .decode("latin-1")
    )


def build_pdf_bytes(
    review: Dict[str, Any],
    code: str,
    language: str,
    filename: str = "snippet",
) -> bytes:
    """Generate PDF report as bytes."""
    pdf = ReviewPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, f"File: {filename}  |  Language: {language}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0,
        6,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(0, 6, f"Rating: {review.get('rating', 0)}/10", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.section_title("Summary")
    pdf.body_text(review.get("summary", ""))

    pdf.section_title("Time Complexity")
    pdf.body_text(review.get("time_complexity", "N/A"))

    pdf.section_title("Complexity Analysis")
    pdf.body_text(review.get("complexity_analysis", ""))

    for title, key in [
        ("Issues", "issues"),
        ("Bugs", "bugs"),
        ("Security", "security"),
        ("Performance", "performance"),
    ]:
        items = review.get(key) or []
        if items:
            pdf.section_title(title)
            for i, item in enumerate(items[:15], 1):
                line = (
                    f"{i}. [{item.get('severity', 'Low')}] "
                    f"{item.get('title', item.get('name', 'Item'))}"
                )
                pdf.body_text(line)
                if item.get("description"):
                    pdf.body_text(f"   {item['description']}")

    pdf.section_title("Optimized Code (excerpt)")
    opt = review.get("optimized_code", "")[:3000]
    pdf.body_text(opt or "(not provided)")

    buffer = io.BytesIO()
    pdf.output(buffer)
    return buffer.getvalue()


def truncate_history_entry(entry: Dict[str, Any], max_code: int = 200) -> Dict[str, Any]:
    """Store compact history item in session state."""
    return {
        "timestamp": entry.get("timestamp"),
        "filename": entry.get("filename"),
        "language": entry.get("language"),
        "rating": entry.get("rating"),
        "summary": (entry.get("summary") or "")[:300],
        "code_preview": (entry.get("code") or "")[:max_code],
    }


def merge_issue_lists(review: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Combine all issue-like lists for metrics."""
    combined: List[Dict[str, Any]] = []
    for key in ("issues", "bugs", "security", "performance", "optimization", "readability"):
        for item in review.get(key) or []:
            if isinstance(item, dict):
                combined.append(item)
    return combined
