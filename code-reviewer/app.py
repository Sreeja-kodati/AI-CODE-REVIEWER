import os
import re
import uuid
import json
import shutil
import logging
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from utils.ui_components import (
    set_dark_mode,
    render_header,
    render_sidebar,
    render_issue_expander,
)
from utils.code_parser import detect_language
from utils.static_analysis import run_static_analysis
from utils.security_checker import run_security_scan
from models.ai_reviewer import AIReviewer
from utils.report_generator import build_review_markdown, save_review_report_artifacts


from database.db import Database


LOGGER = logging.getLogger("code-reviewer")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


SUPPORTED_LANGUAGES = {
    "auto": "Auto",
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "c": "C",
    "cpp": "C++",
    "sql": "SQL",
    "html": "HTML",
    "css": "CSS",
    "go": "Go",
}


def _safe_filename(name: str) -> str:
    name = name.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_\-.]", "", name)[:120] or "code"


def _init_state() -> None:
    if "review_result" not in st.session_state:
        st.session_state.review_result = None
    if "review_history" not in st.session_state:
        st.session_state.review_history = []


def run_review_pipeline(
    db: Database,
    user_id: int,
    source_type: str,
    source_ref: str,
    filename: str,
    code: str,
    language: str,
) -> Dict[str, Any]:
    """
    Run the end-to-end review pipeline and persist results.

    Args:
        db: Database instance.
        user_id: Current user ID.
        source_type: input type (paste/upload/zip/github/repo/pr).
        source_ref: opaque identifier (e.g., file name or GitHub ref).
        filename: display filename.
        code: full source code payload.
        language: language identifier.

    Returns:
        Structured review result dictionary.
    """
    correlation_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    # Basic sanitation before sending to AI
    # - strip extremely sensitive-looking patterns
    # - keep it deterministic and minimal for now
    sanitized = re.sub(r"(-----BEGIN (?:RSA|EC|OPENSSH|PGP) PRIVATE KEY-----[\s\S]+?-----END \1PRIVATE KEY-----)",
                        "[REDACTED_KEY]", code, flags=re.IGNORECASE)
    sanitized = re.sub(r"\b(password|passwd|secret|token)\b\s*[:=]\s*['\"][^'\"]+['\"]",
                        lambda m: f"{m.group(1)}: '[REDACTED]'", sanitized, flags=re.IGNORECASE)

    detected_language = detect_language(sanitized, override=language)
    static_results = run_static_analysis(sanitized, detected_language)
    security_results = run_security_scan(sanitized, detected_language)

    ai = AIReviewer()
    ai_results = ai.review(
        source_code=sanitized,
        language=detected_language,
        static_analysis=static_results,
        security_analysis=security_results,
        correlation_id=correlation_id,
    )

    # Compute scores from normalized findings
    quality_score, security_score = ai.compute_scores(
        static_analysis=static_results,
        security_analysis=security_results,
        ai_issues=ai_results.get("issues", []),
    )

    review_result = {
        "correlation_id": correlation_id,
        "timestamp": started_at,
        "source_type": source_type,
        "source_ref": source_ref,
        "filename": filename,
        "language": detected_language,
        "scores": {
            "quality_score": quality_score,
            "security_score": security_score,
        },
        "static_analysis": static_results,
        "security_analysis": security_results,
        "ai": ai_results,
    }

    # Persist review
    review_id = db.insert_review(
        user_id=user_id,
        filename=filename,
        language=detected_language,
        review_result=review_result,
        source_type=source_type,
        source_ref=source_ref,
    )

    # Save artifacts (markdown + pdf-ready HTML later)
    save_review_report_artifacts(
        review_id=review_id,
        review_result=review_result,
        out_dir=os.path.join("reports", str(review_id)),
    )

    review_result["review_id"] = review_id
    return review_result


def main() -> None:
    st.set_page_config(page_title="AI Code Reviewer", layout="wide")
    _init_state()

    db = Database()

    # Auth
    user = db.require_login_ui()
    if not user:
        st.stop()

    set_dark_mode()

    render_header()
    render_sidebar(db, user)

    # Main input
    tab1, tab2 = st.tabs(["Paste / Text", "Upload / GitHub (best-effort skeleton)"])

    with tab1:
        st.subheader("Paste code")
        language_hint = st.selectbox(
            "Language (or Auto)", options=list(SUPPORTED_LANGUAGES.keys()), index=0
        )
        code = st.text_area("Source code", height=420, placeholder="Paste your code here...")

        colA, colB = st.columns([1, 1])
        with colA:
            filename = st.text_input("Filename (for context)", value="snippet.py")
        with colB:
            # Keep reference stable for history
            source_ref = st.text_input("Source ref (optional)", value="paste://" + filename)

        run_btn = st.button("Run Review", type="primary", use_container_width=True)

        if run_btn:
            if not code.strip():
                st.error("Please paste some code.")
                return

            with st.spinner("Analyzing..."):
                result = run_review_pipeline(
                    db=db,
                    user_id=user["id"],
                    source_type="paste",
                    source_ref=source_ref.strip(),
                    filename=_safe_filename(filename),
                    code=code,
                    language=language_hint,
                )
                st.session_state.review_result = result

    with tab2:
        st.subheader("Upload files / zip / GitHub")
        st.info(
            "This skeleton implements local upload and paste. GitHub/zip review hooks are included as UI placeholders."
        )
        st.warning("To keep this production-ready baseline runnable, zip/GitHub are wired as extensible hooks but may require tokens.")
        uploaded_files = st.file_uploader(
            "Upload one or more code files", type=["py", "java", "js", "jsx", "ts", "c", "cpp", "sql", "html", "css", "go"],
            accept_multiple_files=True,
        )

        language_hint = st.selectbox(
            "Language (or Auto)", options=list(SUPPORTED_LANGUAGES.keys()), index=0
        )

        run_btn = st.button("Run Review (uploads)", use_container_width=True)

        if run_btn and uploaded_files:
            # Best-effort: concatenate files into a multi-file pseudo payload
            payload_parts: List[str] = []
            first_name = uploaded_files[0].name
            for f in uploaded_files:
                content = f.read().decode("utf-8", errors="replace")
                payload_parts.append(f"\n\n# ===== FILE: {f.name} =====\n{content}")
            combined = "\n".join(payload_parts)
            with st.spinner("Analyzing uploaded files..."):
                result = run_review_pipeline(
                    db=db,
                    user_id=user["id"],
                    source_type="upload",
                    source_ref="upload://" + first_name,
                    filename=_safe_filename(first_name),
                    code=combined,
                    language=language_hint,
                )
                st.session_state.review_result = result

    # Output
    st.divider()
    st.subheader("Review Output")
    review_result = st.session_state.review_result
    if not review_result:
        st.caption("Run a review to see results.")
        st.stop()

    scores = review_result.get("scores", {})
    st.metric("Quality Score", f"{scores.get('quality_score', 0)}/100")
    st.metric("Security Score", f"{scores.get('security_score', 0)}/100")

    st.write("### Static Analysis Summary")
    st.json(review_result.get("static_analysis", {}))

    st.write("### Security Analysis Summary")
    st.json(review_result.get("security_analysis", {}))

    ai = review_result.get("ai", {})
    issues = ai.get("issues", [])
    improved_code = ai.get("improved_code")

    st.write("### Issues (AI + Heuristics)")
    for issue in issues[:200]:
        render_issue_expander(issue)

    if improved_code:
        st.write("### Improved Code (best-effort)")
        st.code(improved_code, language=review_result.get("language", ""))
    else:
        st.caption("No improved code generated (guardrails may have prevented full rewrites).")

    st.write("### Review Notes")
    st.write(ai.get("notes", ""))

    # Download: HTML/Markdown text (PDF generation hooks in report generator)
    st.write("### Download Report")
    review_id = review_result.get("review_id")
    if review_id:
        md = build_review_markdown(review_result)
        st.download_button(
            label="Download Markdown report",
            data=md,
            file_name=f"review_{review_id}.md",
            mime="text/markdown",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
