import logging
from typing import Any, Dict, List, Tuple

LOGGER = logging.getLogger("code-reviewer.ai")


class AIReviewer:
    """AI review engine.

    Deterministic baseline:
    - No local transformer loading
    - No external AI provider calls
    - Produces structured review from static + security findings
    """

    def __init__(self) -> None:
        pass

    def _rubric_review(
        self,
        *,
        language: str,
        static_analysis: Dict[str, Any],
        security_analysis: Dict[str, Any],
        correlation_id: str,
    ) -> Dict[str, Any]:
        """Create structured issues and scores from analyzer outputs."""
        _ = language, correlation_id

        issues: List[Dict[str, Any]] = []

        for item in (security_analysis or {}).get("issues", []):
            issues.append(
                {
                    "severity": item.get("severity", "High"),
                    "title": item.get("title", "Security issue"),
                    "rule_id": item.get("rule_id"),
                    "line": item.get("line"),
                    "description": item.get("description"),
                    "explanation": item.get("explanation")
                    or "Identified by security heuristics.",
                    "suggested_fix": item.get("suggested_fix"),
                }
            )

        for item in (static_analysis or {}).get("issues", []):
            issues.append(
                {
                    "severity": item.get("severity", "Medium"),
                    "title": item.get("title", "Code quality issue"),
                    "rule_id": item.get("rule_id"),
                    "line": item.get("line"),
                    "description": item.get("message"),
                    "explanation": "Static analyzer warning based on provided tooling.",
                    "suggested_fix": item.get("suggested_fix"),
                }
            )

        quality_score = int(
            max(0, 100 - (len(static_analysis.get("issues", [])) * 2))
        )
        security_score = int(
            max(0, 100 - (len(security_analysis.get("issues", [])) * 7))
        )

        return {
            "issues": issues,
            "improved_code": None,
            "notes": "Deterministic baseline engaged (no AI model invoked).",
            "quality_score": quality_score,
            "security_score": security_score,
        }

    def review(
        self,
        *,
        source_code: str,
        language: str,
        static_analysis: Dict[str, Any],
        security_analysis: Dict[str, Any],
        correlation_id: str,
    ) -> Dict[str, Any]:
        """Generate structured review (deterministic)."""
        _ = source_code
        return self._rubric_review(
            language=language,
            static_analysis=static_analysis,
            security_analysis=security_analysis,
            correlation_id=correlation_id,
        )

    def compute_scores(
        self,
        *,
        static_analysis: Dict[str, Any],
        security_analysis: Dict[str, Any],
        ai_issues: List[Dict[str, Any]],
    ) -> Tuple[int, int]:
        """Compatibility scoring hook (not used by deterministic review)."""
        quality_issues = len(static_analysis.get("issues", []))
        security_issues = len(security_analysis.get("issues", []))

        sev_weight = {"Critical": 20, "High": 12, "Medium": 6, "Low": 3}
        for iss in ai_issues:
            sev = (iss.get("severity") or "Medium").title()
            if sev in sev_weight:
                security_issues += 1

        quality_score = max(0, min(100, int(100 - quality_issues * 2)))
        security_score = max(0, min(100, int(100 - security_issues * 5)))
        return quality_score, security_score
