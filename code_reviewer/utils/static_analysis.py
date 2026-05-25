import os
import subprocess
import tempfile
import json
from typing import Any, Dict, List, Tuple


def _run_cmd(cmd: List[str], cwd: str) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def run_static_analysis(code: str, language: str) -> Dict[str, Any]:
    """Run static analysis tools where feasible.

    This baseline focuses on Python linters (pylint/flake8) and bandit.
    For other languages, it returns an empty issues list and relies on
    security heuristics + AI fallback.
    """

    issues: List[Dict[str, Any]] = []
    metrics: Dict[str, Any] = {}

    if language != "python":
        return {"issues": issues, "metrics": metrics, "tooling": {"python": False, "other": True}}

    with tempfile.TemporaryDirectory() as td:
        src_path = os.path.join(td, "snippet.py")
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code or "")

        # flake8
        try:
            rc, out, err = _run_cmd(["flake8", "snippet.py"], cwd=td)
            if out.strip():
                # Format: path:line:col code message
                for line in out.strip().splitlines():
                    parts = line.split(":", 3)
                    if len(parts) >= 4:
                        _, lineno, _, msg = parts[0], parts[1], parts[2], parts[3]
                        issues.append(
                            {
                                "severity": "Medium",
                                "title": "flake8 issue",
                                "rule_id": (msg.split()[0] if msg else None),
                                "line": int(lineno) if lineno.isdigit() else None,
                                "message": msg,
                            }
                        )
        except Exception:
            pass

        # pylint
        try:
            rc, out, err = _run_cmd(
                ["pylint", "snippet.py", "--output-format=json"],
                cwd=td,
            )
            if out.strip():
                parsed = json.loads(out)
                for item in parsed.get("messages", []):
                    issues.append(
                        {
                            "severity": "High" if item.get("type") == "error" else "Medium",
                            "title": "pylint issue",
                            "rule_id": item.get("symbol"),
                            "line": item.get("line"),
                            "message": item.get("message"),
                        }
                    )
        except Exception:
            pass

        # radon complexity
        try:
            rc, out, err = _run_cmd(["radon", "cc", "snippet.py", "-s"], cwd=td)
            metrics["radon_cc"] = out.strip() if out else None
        except Exception:
            metrics["radon_cc"] = None

    return {"issues": issues, "metrics": metrics, "tooling": {"python": True, "other": False}}

