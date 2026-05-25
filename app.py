"""
AI-Powered Automated Code Reviewer — Streamlit frontend.
Powered by the OpenAI API.
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from datetime import datetime

import pandas as pd

from review_engine import REVIEW_CATEGORIES, ReviewEngineError, run_code_review
from utils import (
    DEMO_CODE,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_LANGUAGES,
    build_pdf_bytes,
    build_txt_report,
    count_by_severity,
    detect_language_from_filename,
    highlight_code,
    issues_to_dataframe,
    merge_issue_lists,
    read_uploaded_file,
    severity_icon,
    severity_style,
    truncate_history_entry,
    validate_upload,
)

# ---------------------------------------------------------------------------
# Page config & global styles
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AI Code Reviewer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .main-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 50%, #7c3aed 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        color: white;
        margin-bottom: 1.5rem;
        box-shadow: 0 10px 40px rgba(37, 99, 235, 0.25);
    }
    .main-header h1 { margin: 0; font-size: 2.2rem; font-weight: 700; }
    .main-header p { margin: 0.5rem 0 0; opacity: 0.92; font-size: 1.05rem; }
    .metric-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem 1.25rem;
        text-align: center;
    }
    .severity-high { background: #fef2f2; border-left: 4px solid #ef4444; padding: 12px; border-radius: 8px; margin: 8px 0; }
    .severity-medium { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 12px; border-radius: 8px; margin: 8px 0; }
    .severity-low { background: #f0fdf4; border-left: 4px solid #22c55e; padding: 12px; border-radius: 8px; margin: 8px 0; }
    div[data-testid="stSidebar"] { background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%); }
    div[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    div[data-testid="stSidebar"] .stTextInput label { color: #cbd5e1 !important; }
    .highlight { border-radius: 8px; overflow-x: auto; font-size: 0.85rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 10px 20px;
        font-weight: 600;
    }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def init_session_state() -> None:
    defaults = {
        "review_result": None,
        "review_history": [],
        "last_code": "",
        "last_language": "python",
        "last_filename": "snippet.py",
        "api_key_input": "",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def render_landing_header() -> None:
    st.markdown(
        """
        <div class="main-header">
            <h1>🔍 AI Automated Code Reviewer</h1>
            <p>Professional code analysis powered by <strong>OpenAI</strong> —
            quality, bugs, security, performance &amp; more.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def copy_button(text: str, key: str) -> None:
    """Embed a copy-to-clipboard button."""
    import json as _json

    payload = _json.dumps(text)
    components.html(
        f"""
        <button id="btn_{key}" style="
            background:#2563eb;color:white;border:none;padding:8px 16px;
            border-radius:8px;cursor:pointer;font-weight:600;margin:4px 0;
        ">📋 Copy to Clipboard</button>
        <script>
        const txt = {payload};
        document.getElementById('btn_{key}').onclick = function() {{
            navigator.clipboard.writeText(txt);
            this.innerText = '✓ Copied!';
            setTimeout(() => this.innerText = '📋 Copy to Clipboard', 2000);
        }};
        </script>
        """,
        height=50,
    )


def render_alert(message: str, level: str = "info") -> None:
    icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}
    st.markdown(f"**{icons.get(level, 'ℹ️')} {message}**")


def render_issue_cards(items: list, empty_msg: str = "No issues found.") -> None:
    if not items:
        st.success(empty_msg)
        return
    for item in items:
        sev = str(item.get("severity", "Low")).lower()
        css_class = f"severity-{sev}" if sev in ("low", "medium", "high") else "severity-low"
        title = item.get("title") or item.get("name") or "Issue"
        desc = item.get("description", "")
        fix = item.get("suggested_fix") or item.get("fix", "")
        with st.container():
            st.markdown(
                f'<div class="{css_class}">'
                f"<strong>{severity_icon(item.get('severity'))} {title}</strong> "
                f'<span style="color:{severity_style(item.get("severity"))};font-weight:600;">'
                f'[{item.get("severity", "Low")}]</span><br/>{desc}</div>',
                unsafe_allow_html=True,
            )
            if fix:
                with st.expander("💡 Suggested fix"):
                    st.code(fix, language=None)


def render_sidebar() -> tuple:
    with st.sidebar:
        st.markdown("### ⚙️ Settings")
        api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            value=st.session_state.get("api_key_input", ""),
            help="Get your key at platform.openai.com. Stored only in this session unless set in .env",
            placeholder="sk-...",
        )
        st.session_state.api_key_input = api_key

        st.markdown("---")
        st.markdown("### 🌐 Supported Languages")
        ext_list = ", ".join(sorted(SUPPORTED_EXTENSIONS.keys()))
        st.caption(f"Upload: {ext_list}")
        for lang in SUPPORTED_LANGUAGES:
            st.markdown(f"- `{lang}`")

        st.markdown("---")
        st.markdown("### 📖 About")
        st.markdown(
            """
            **AI Code Reviewer** sends your code to the **OpenAI API** for deep analysis.

            - 6 review categories
            - Severity-ranked issues
            - Optimized code suggestions
            - PDF & TXT exports
            - Session review history
            """
        )
        st.caption("Built with Python + Streamlit")

    return api_key


def render_input_section() -> None:
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("📁 Upload Code File")
        uploaded = st.file_uploader(
            "Drag & drop or browse",
            type=[e.lstrip(".") for e in SUPPORTED_EXTENSIONS],
            help="Supported: .py, .js, .java, .cpp, .html, .css",
        )
        if uploaded:
            ok, msg = validate_upload(uploaded.name)
            if ok:
                try:
                    content, lang = read_uploaded_file(uploaded)
                    st.session_state.last_code = content
                    st.session_state.last_language = lang
                    st.session_state.last_filename = uploaded.name
                    st.success(f"Loaded **{uploaded.name}** ({lang})")
                except ValueError as exc:
                    st.error(str(exc))
            else:
                st.error(msg)

    with col_right:
        st.subheader("✏️ Or Paste Code")
        if st.button("📝 Load Demo Sample", use_container_width=True):
            st.session_state.last_code = DEMO_CODE
            st.session_state.last_language = "python"
            st.session_state.last_filename = "demo_sample.py"
            st.rerun()

        lang_options = ["auto"] + SUPPORTED_LANGUAGES
        default_lang = st.session_state.last_language
        idx = lang_options.index(default_lang) if default_lang in lang_options else 0
        selected_lang = st.selectbox("Language", lang_options, index=idx)

    st.markdown("### 💻 Code Editor")
    code = st.text_area(
        "Source code",
        value=st.session_state.last_code,
        height=320,
        label_visibility="collapsed",
        placeholder="Paste your code here...",
    )
    st.session_state.last_code = code

    if selected_lang == "auto":
        from utils import guess_language_from_code

        st.session_state.last_language = guess_language_from_code(code)
    else:
        st.session_state.last_language = selected_lang

    st.caption(f"Detected / selected: **{st.session_state.last_language}**")

    st.markdown("### 🏷️ Review Categories")
    selected_categories = []
    cols = st.columns(3)
    for i, cat in enumerate(REVIEW_CATEGORIES):
        with cols[i % 3]:
            if st.checkbox(cat, value=True, key=f"cat_{cat}"):
                selected_categories.append(cat)

    return code, selected_categories


def render_metrics(review: dict) -> None:
    all_issues = merge_issue_lists(review)
    counts = count_by_severity(all_issues)
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Final Score", f"{review.get('rating', 0)}/10")
    with c2:
        st.metric("Total Issues", len(all_issues))
    with c3:
        st.metric("High", counts["High"], delta=None)
    with c4:
        st.metric("Medium", counts["Medium"])
    with c5:
        st.metric("Low", counts["Low"])


def render_results(review: dict, code: str) -> None:
    render_metrics(review)

    tab_summary, tab_bugs, tab_security, tab_opt, tab_score = st.tabs(
        ["📋 Summary", "🐛 Bugs", "🔒 Security", "⚡ Optimization", "⭐ Final Score"]
    )

    with tab_summary:
        st.markdown("#### Overview")
        st.info(review.get("summary", ""))
        st.markdown("#### ⏱️ Time Complexity")
        st.write(review.get("time_complexity", ""))
        st.markdown("#### 📊 Complexity Analysis")
        st.write(review.get("complexity_analysis", ""))

        smells = review.get("code_smells", [])
        if smells:
            st.markdown("#### 👃 Code Smells")
            render_issue_cards(smells, "No code smells detected.")
        else:
            st.success("No significant code smells detected.")

        st.markdown("#### 📌 All Issues")
        df = issues_to_dataframe(review.get("issues", []))
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
        render_issue_cards(review.get("issues", []), "No general issues reported.")

        if review.get("optimized_code"):
            st.markdown("#### ✨ Optimized Code")
            with st.expander("View optimized version", expanded=False):
                st.code(review["optimized_code"], language=st.session_state.last_language)
                copy_button(review["optimized_code"], "opt_code")

    with tab_bugs:
        st.markdown("#### Bug Detection")
        render_issue_cards(review.get("bugs", []), "No bugs detected — great job!")
        bug_df = issues_to_dataframe(review.get("bugs", []))
        if not bug_df.empty:
            st.dataframe(bug_df, use_container_width=True, hide_index=True)

    with tab_security:
        st.markdown("#### Security Issues")
        sec = review.get("security", [])
        if sec:
            st.warning(f"Found **{len(sec)}** security concern(s).")
        render_issue_cards(sec, "No security vulnerabilities detected.")
        sec_df = issues_to_dataframe(sec)
        if not sec_df.empty:
            st.dataframe(sec_df, use_container_width=True, hide_index=True)

    with tab_opt:
        st.markdown("#### Performance Suggestions")
        render_issue_cards(
            review.get("performance", []) + review.get("optimization", []),
            "No performance improvements suggested.",
        )
        st.markdown("#### Readability & Best Practices")
        render_issue_cards(review.get("readability", []), "No readability issues.")

        if review.get("optimized_code"):
            st.markdown("#### Optimized Code")
            html = highlight_code(
                review["optimized_code"], st.session_state.last_language
            )
            st.markdown(html, unsafe_allow_html=True)
            copy_button(review["optimized_code"], "opt_tab")

    with tab_score:
        rating = review.get("rating", 0)
        st.markdown(f"## ⭐ AI Rating: **{rating} / 10**")
        progress = rating / 10.0
        st.progress(progress)
        if rating >= 8:
            st.success("Excellent code quality!")
        elif rating >= 6:
            st.info("Good foundation — address medium/high issues to improve.")
        elif rating >= 4:
            st.warning("Needs improvement — review suggested fixes.")
        else:
            st.error("Significant issues found — prioritize high-severity items.")

        st.markdown("#### Issue Breakdown")
        all_issues = merge_issue_lists(review)
        if all_issues:
            breakdown = pd.DataFrame(
                [{"Category": i.get("category", "General"), "Severity": i.get("severity", "Low")}
                 for i in all_issues if i.get("category")]
            )
            if not breakdown.empty:
                st.bar_chart(breakdown.groupby("Severity").size())

    # Downloads
    st.markdown("---")
    st.subheader("📥 Export Report")
    txt = build_txt_report(
        review, code, st.session_state.last_language, st.session_state.last_filename
    )
    pdf_bytes = build_pdf_bytes(
        review, code, st.session_state.last_language, st.session_state.last_filename
    )
    d1, d2, d3 = st.columns(3)
    with d1:
        st.download_button(
            "⬇️ Download TXT",
            txt,
            file_name=f"review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with d2:
        st.download_button(
            "⬇️ Download PDF",
            pdf_bytes,
            file_name=f"review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    with d3:
        copy_button(txt[:5000], "report_snippet")


def render_history() -> None:
    history = st.session_state.review_history
    if not history:
        return
    st.markdown("---")
    st.subheader("📜 Review History (this session)")
    for i, entry in enumerate(reversed(history[-10:])):
        with st.expander(
            f"{entry.get('timestamp')} — {entry.get('filename')} "
            f"(⭐ {entry.get('rating')}/10)"
        ):
            st.write(entry.get("summary", ""))
            st.caption(entry.get("code_preview", ""))


def main() -> None:
    init_session_state()
    api_key = render_sidebar()
    render_landing_header()

    code, categories = render_input_section()

    st.markdown("")
    review_clicked = st.button(
        "🚀 Review Code",
        type="primary",
        use_container_width=True,
    )

    if review_clicked:
        if not code or not code.strip():
            st.error("Please paste code or upload a file before reviewing.")
        elif not categories:
            st.warning("Select at least one review category.")
        else:
            with st.spinner("🤖 OpenAI is analyzing your code... This may take up to a minute."):
                try:
                    result = run_code_review(
                        code=code,
                        language=st.session_state.last_language,
                        categories=categories,
                        api_key=api_key or None,
                    )
                    st.session_state.review_result = result
                    entry = truncate_history_entry(
                        {
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "filename": st.session_state.last_filename,
                            "language": st.session_state.last_language,
                            "rating": result.get("rating"),
                            "summary": result.get("summary"),
                            "code": code,
                        }
                    )
                    st.session_state.review_history.append(entry)
                    st.success("Review complete!")
                except ReviewEngineError as exc:
                    st.error(str(exc))
                    if exc.status_code == 429:
                        st.info(
                            "**Why this happens:** Each review sends a large prompt to OpenAI "
                            "(full code + detailed JSON report). Free or new accounts hit limits quickly.\n\n"
                            "**Try:** Wait 1–2 minutes → use shorter code → add billing at "
                            "[platform.openai.com/billing](https://platform.openai.com/settings/organization/billing) "
                            "→ check [usage](https://platform.openai.com/usage)."
                        )
                except Exception as exc:
                    st.error(f"Unexpected error: {exc}")

    if st.session_state.review_result:
        st.markdown("---")
        st.header("📊 Review Results")
        render_results(st.session_state.review_result, code)

    render_history()


if __name__ == "__main__":
    main()
