import os
from typing import Any, Dict


def build_review_markdown(review_result: Dict[str, Any]) -> str:
    """Build a markdown report."""
    rid = review_result.get("review_id") or ""
    filename = review_result.get("filename")
    language = review_result.get("language")

    scores = review_result.get("scores", {})
    quality = scores.get("quality_score")
    security = scores.get("security_score")

    static_issues = (review_result.get("static_analysis", {}) or {}).get("issues", [])
    security_issues = (review_result.get("security_analysis", {}) or {}).get("issues", [])

    ai_issues = (review_result.get("ai", {}) or {}).get("issues", [])

    lines = [
        f"# AI Code Review Report {rid}",
        "",
        f"**File:** {filename}",
        f"**Language:** {language}",
        f"**Quality Score:** {quality}/100",
        f"**Security Score:** {security}/100",
        "",
        "---",
        "",
        "## Static Analysis Issues",
    ]

    if not static_issues:
        lines.append("- None")
    else:
        for i in static_issues[:200]:
            lines.append(f"- {i.get('severity')}: {i.get('message')} (rule: {i.get('rule_id')})")

    lines.append("")
    lines.append("## Security Issues")
    if not security_issues:
        lines.append("- None")
    else:
        for i in security_issues[:200]:
            lines.append(
                f"- {i.get('severity')}: {i.get('title')} (rule: {i.get('rule_id')})"
            )

    lines.append("")
    lines.append("## AI Issues (Structured)")
    if not ai_issues:
        lines.append("- None")
    else:
        for i in ai_issues[:300]:
            lines.append(f"### {i.get('severity')}: {i.get('title')}")
            if i.get("line"):
                lines.append(f"- Line: {i['line']}")
            if i.get("description"):
                lines.append(i["description"])
            if i.get("suggested_fix"):
                lines.append(f"**Suggested Fix:** {i['suggested_fix']}")
            lines.append("")

    notes = (review_result.get("ai", {}) or {}).get("notes")
    if notes:
        lines.append("## Notes")
        lines.append(notes)

    return "\n".join(lines)


def save_review_report_artifacts(*, review_id: int, review_result: Dict[str, Any], out_dir: str) -> None:
    """Save markdown (and later PDF) artifacts.

    PDF generation is included as a best-effort extension.
    """
    os.makedirs(out_dir, exist_ok=True)
    md = build_review_markdown({**review_result, "review_id": review_id})

    md_path = os.path.join(out_dir, f"review_{review_id}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    # Best-effort PDF stub: avoid heavy dependencies; generate HTML-ready text.
    # The UI currently offers Markdown download.
    html_path = os.path.join(out_dir, f"review_{review_id}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write("<html><body><pre>" + md.replace("<", "<").replace(">", ">") + "</pre></body></html>")

