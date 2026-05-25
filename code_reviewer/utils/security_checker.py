import os
import re
import subprocess
import tempfile
from typing import Any, Dict, List


def _append_issue(
    issues: List[Dict[str, Any]],
    *,
    severity: str,
    title: str,
    description: str,
    rule_id: str,
    line: int | None = None,
    explanation: str = "",
    suggested_fix: str = "",
) -> None:
    issues.append(
        {
            "severity": severity,
            "title": title,
            "description": description,
            "rule_id": rule_id,
            "line": line,
            "explanation": explanation,
            "suggested_fix": suggested_fix,
        }
    )


def _detect_sql_injection(code: str, issues: List[Dict[str, Any]]) -> None:
    # Basic heuristics
    if re.search(r"execute\(f?['\"]", code, re.I) or re.search(
        r"(format|%s)\s*\).*execute\(", code, re.I
    ):
        _append_issue(
            issues,
            severity="Critical",
            title="Potential SQL Injection",
            description="String formatting or concatenation detected near SQL execution.",
            rule_id="SEC_SQLI",
            explanation="This pattern often leads to tainted input being interpolated into SQL queries.",
            suggested_fix="Use parameterized queries / prepared statements and avoid building SQL with string formatting.",
        )


def _detect_hardcoded_secrets(code: str, issues: List[Dict[str, Any]]) -> None:
    patterns = [
        (r"(?i)api[_-]?key\s*[:=]\s*['\"][^'\"]+['\"]", "SEC_SECRET_APIKEY"),
        (r"(?i)(password|passwd|secret|token)\s*[:=]\s*['\"][^'\"]+['\"]", "SEC_SECRET_PASSWORD"),
    ]
    for pat, rid in patterns:
        m = re.search(pat, code)
        if m:
            _append_issue(
                issues,
                severity="Critical",
                title="Hardcoded credential",
                description="Hardcoded secret-like value detected in source.",
                rule_id=rid,
                line=None,
                explanation="Secrets should never be committed to source code.",
                suggested_fix="Move secrets to environment variables or a secret manager; rotate the exposed credentials.",
            )


def _detect_unsafe_file_ops(code: str, issues: List[Dict[str, Any]]) -> None:
    if re.search(r"os\.system\(|subprocess\.Popen\(|subprocess\.run\(", code):
        _append_issue(
            issues,
            severity="High",
            title="Command execution risk",
            description="Potentially unsafe command execution usage detected.",
            rule_id="SEC_CMD",
            suggested_fix="Avoid shell=True; validate/escape inputs; use allowlists; use safer APIs.",
        )


def _detect_xss(code: str, issues: List[Dict[str, Any]]) -> None:
    # Very basic HTML injection sinks
    if re.search(r"innerHTML\s*=|dangerouslySetInnerHTML", code) or re.search(r"<script", code, re.I):
        _append_issue(
            issues,
            severity="High",
            title="Potential XSS",
            description="Possible HTML/JS injection sink detected.",
            rule_id="SEC_XSS",
            suggested_fix="Escape/encode untrusted input; use safe templating; avoid innerHTML for untrusted data.",
        )


def _run_bandit_if_python(code: str, issues: List[Dict[str, Any]]) -> None:
    if "import" not in code.lower():
        return

    with tempfile.TemporaryDirectory() as td:
        src_path = os.path.join(td, "snippet.py")
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code or "")

        try:
            # bandit output JSON
            proc = subprocess.run(
                ["bandit", "-f", "json", "-q", "snippet.py"],
                cwd=td,
                capture_output=True,
                text=True,
            )
            if proc.stdout.strip():
                import json

                data = json.loads(proc.stdout)
                for item in data.get("results", []):
                    issues.append(
                        {
                            "severity": item.get("issue_severity", "Medium"),
                            "title": item.get("issue_text", "bandit issue"),
                            "description": item.get("issue_text"),
                            "rule_id": item.get("test_name"),
                            "line": item.get("line"),
                            "explanation": item.get("issue_confidence", ""),
                            "suggested_fix": "Review bandit finding and apply safe patterns.",
                        }
                    )
        except Exception:
            return


def run_security_scan(code: str, language: str) -> Dict[str, Any]:
    """Run security scanning and return normalized findings."""

    issues: List[Dict[str, Any]] = []

    # Universal heuristics
    _detect_hardcoded_secrets(code or "", issues)
    _detect_sql_injection(code or "", issues)
    _detect_unsafe_file_ops(code or "", issues)
    _detect_xss(code or "", issues)

    # Python-only SAST hook
    if language == "python":
        _run_bandit_if_python(code or "", issues)

    return {"issues": issues, "tooling": {"bandit": language == "python"}}

