import streamlit as st


def set_dark_mode() -> None:
    """Enable dark mode by injecting CSS into Streamlit."""
    if st.session_state.get("dark_mode") is True:
        st.markdown(
            """
            <style>
            body { background-color: #0f1117; color: #e6edf3; }
            .stTextInput input, .stTextArea textarea, .stSelectbox div { background-color: #161b22; color: #e6edf3; }
            </style>
            """,
            unsafe_allow_html=True,
        )


def render_header() -> None:
    """Render app header."""
    st.title("AI-Powered Automated Code Reviewer")
    st.caption("Static analysis + security heuristics + AI explanations (guardrailed).")


def render_issue_expander(issue: dict) -> None:
    """Render a single issue as an expander."""
    severity = (issue.get("severity") or "Medium").title()
    rule_id = issue.get("rule_id") or issue.get("id") or ""
    headline = f"{severity}: {issue.get('title','Issue')}" + (f" ({rule_id})" if rule_id else "")

    with st.expander(headline, expanded=False):
        if issue.get("line"):
            st.write(f"Line: {issue['line']}")
        if issue.get("description"):
            st.write("**Description:**")
            st.write(issue["description"])
        if issue.get("explanation"):
            st.write("**Explanation:**")
            st.write(issue["explanation"])
        if issue.get("suggested_fix"):
            st.write("**Suggested Fix:**")
            st.write(issue["suggested_fix"])
        if issue.get("improved_code"):
            st.write("**Improved Code:**")
            st.code(issue["improved_code"])


def render_sidebar(db, user) -> None:
    """Render sidebar: account and history."""
    with st.sidebar:
        st.markdown("## Account")
        st.write(f"Logged in as: **{user.get('email')}**")
        st.session_state["dark_mode"] = st.toggle("Dark mode", value=True)
        render_history(db, user)


def render_history(db, user) -> None:
    """Render last reviews for quick navigation."""
    st.markdown("## Review History")
    history = db.list_reviews(user["id"], limit=20)

    if not history:
        st.caption("No history yet.")
        return

    for r in history:
        label = f"{r['filename']} • {r['language']} • {r['created_at'][:19].replace('T', ' ')}"
        with st.expander(label, expanded=False):
            st.write(f"Review ID: {r['id']}")
            st.write(
                "Scores: "
                f"Quality {r.get('quality_score',0)}/100 • "
                f"Security {r.get('security_score',0)}/100"
            )

