import re
from typing import Dict, List

import rapidfuzz

# Directories to ignore during parsing/analysis.
IGNORE_DIRS = {
    ".git",
    "venv",
    ".venv",
    "node_modules",
    "__pycache__",
    ".idea",
    ".vscode",
    "dist",
    "build",
}


def detect_language(code: str, override: str = "auto") -> str:
    """Detect language using heuristics or override.

    Args:
        code: Source code.
        override: 'auto' or explicit language key.

    Returns:
        Normalized language key used throughout pipeline.
    """

    normalized = (override or "auto").lower().strip()
    if normalized != "auto":
        mapping = {
            "c++": "cpp",
            "c#": "c",
            "html/css": "html",
            "javascript": "javascript",
            "js": "javascript",
        }
        return mapping.get(normalized, normalized)

    sample = (code or "").lower()[:20000]

    if "def " in sample and "import " in sample:
        return "python"
    if re.search(r"\bpackage\s+", sample) and re.search(r"\bclass\s+", sample):
        return "java"
    if "function " in sample and ("console.log" in sample or "=>" in sample):
        return "javascript"
    if re.search(r"#include\s*<", sample) and re.search(r"\bint\s+main\s*\(", sample):
        return "c"
    if "std::" in sample or re.search(r"\bvector<", sample):
        return "cpp"
    if re.search(r"\b(select|insert|update|delete)\b", sample):
        return "sql"
    if "<!doctype html" in sample or "<html" in sample:
        return "html"
    if "package-lock.json" in sample or "import\"http\"" in sample:
        return "javascript"
    if re.search(r"\bfunc\s+\w+\s*\(", sample) and "package " in sample:
        return "go"

    return "auto"


def should_ignore_path(path: str) -> bool:
    """Return True if a path should be ignored for analysis."""

    parts = set(path.replace("\\", "/").split("/"))
    return any(p in IGNORE_DIRS for p in parts)


def normalize_newlines(code: str) -> str:
    """Normalize CRLF to LF."""

    return (code or "").replace("\r\n", "\n").replace("\r", "\n")


def parse_input_code(payload: str, *, max_chars: int = 1_000_000) -> str:
    """Normalize and bound the incoming code payload.

    Args:
        payload: Incoming source code.
        max_chars: Maximum allowed characters.

    Returns:
        Normalized code (possibly truncated with head/tail context).
    """

    code = normalize_newlines(payload or "")
    if len(code) <= max_chars:
        return code

    # Keep head/tail for better context.
    head = code[: int(max_chars * 0.7)]
    tail = code[-int(max_chars * 0.3) :]
    return f"{head}\n\n[...TRUNCATED...]\n\n{tail}"


def extract_symbols(code: str, language: str) -> Dict[str, List[str]]:
    """Lightweight symbol extraction for analysis context.

    This is intentionally best-effort and language-agnostic.

    Returns:
        Dictionary with keys: functions, classes, imports.
    """

    text = code or ""
    symbols: Dict[str, List[str]] = {"functions": [], "classes": [], "imports": []}

    if language == "python":
        symbols["functions"] = re.findall(
            r"^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text, re.M
        )
        symbols["classes"] = re.findall(
            r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(?", text, re.M
        )
        symbols["imports"] = re.findall(
            r"^(?:from\s+\S+\s+import\s+|import\s+)(\S+)", text, re.M
        )

    elif language in {"java", "javascript", "go"}:
        symbols["functions"] = re.findall(
            r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\b", text
        )
        symbols["classes"] = re.findall(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\b", text)

    return symbols


def detect_duplicate_chunks(
    code: str, *, chunk_size_lines: int = 80, min_similarity: int = 90
) -> List[Dict[str, int]]:
    """Heuristic duplicate detection using fuzzy matching on chunks.

    Args:
        code: Full code.
        chunk_size_lines: Lines per chunk.
        min_similarity: Fuzzy similarity threshold.

    Returns:
        List of dicts with duplicate range metadata.
    """

    lines = (code or "").splitlines()
    if not lines:
        return []

    chunks: List[tuple[int, str]] = []
    for i in range(0, len(lines), chunk_size_lines):
        chunk = "\n".join(lines[i : i + chunk_size_lines]).strip()
        if chunk:
            chunks.append((i, chunk))

    duplicates: List[Dict[str, int]] = []
    for idx_a in range(len(chunks)):
        for idx_b in range(idx_a + 1, len(chunks)):
            a_line, a = chunks[idx_a]
            b_line, b = chunks[idx_b]
            if not a or not b:
                continue
            score = rapidfuzz.fuzz.token_set_ratio(a, b)
            if score >= min_similarity:
                duplicates.append(
                    {
                        "a_start_line": a_line + 1,
                        "b_start_line": b_line + 1,
                        "similarity": score,
                    }
                )

    return duplicates

