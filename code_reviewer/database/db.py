import os
import re
import json
import sqlite3
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import bcrypt


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class Database:
    """SQLite persistence layer with simple session-based auth UI."""

    def __init__(self) -> None:
        import streamlit as st

        self.db_path = os.getenv("DB_PATH", os.path.join("data", "reviewer.sqlite"))
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

        # UI state
        if "user" not in st.session_state:
            st.session_state["user"] = None

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              email TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              filename TEXT,
              language TEXT,
              review_result_json TEXT NOT NULL,
              quality_score INTEGER NOT NULL,
              security_score INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              source_type TEXT,
              source_ref TEXT,
              FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        self.conn.commit()

    def _hash_password(self, password: str) -> str:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def _verify_password(self, password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except Exception:
            return False

    def create_user(self, *, name: str, email: str, password: str) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO users (name,email,password_hash,created_at) VALUES (?,?,?,?)",
            (name, email.lower().strip(), self._hash_password(password), _now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (email.lower().strip(),))
        row = cur.fetchone()
        return dict(row) if row else None

    def insert_review(
        self,
        *,
        user_id: int,
        filename: str,
        language: str,
        review_result: Dict[str, Any],
        source_type: str,
        source_ref: str,
    ) -> int:
        scores = review_result.get("scores", {})
        quality = int(scores.get("quality_score", 0))
        security = int(scores.get("security_score", 0))
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO reviews (user_id,filename,language,review_result_json,quality_score,security_score,created_at,source_type,source_ref)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                user_id,
                filename,
                language,
                json.dumps(review_result, ensure_ascii=False),
                quality,
                security,
                _now_iso(),
                source_type,
                source_ref,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_reviews(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, filename, language, quality_score, security_score, created_at
            FROM reviews
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]

    def require_login_ui(self) -> Optional[Dict[str, Any]]:
        """Render login/register and return user dict if logged in."""
        import streamlit as st

        if st.session_state.get("user"):
            return st.session_state["user"]

        st.subheader("Login / Register")
        mode = st.radio("Mode", ["Login", "Register"], horizontal=True)

        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        name = st.text_input("Name (register only)")

        if st.button(mode, use_container_width=True):
            if not email or not password:
                st.error("Email and password required.")
                return None

            if mode == "Login":
                u = self.get_user_by_email(email)
                if not u or not self._verify_password(password, u["password_hash"]):
                    st.error("Invalid credentials.")
                    return None
                st.session_state["user"] = {k: u[k] for k in ("id", "email", "name")}
                return st.session_state["user"]

            # Register
            if not name:
                st.error("Name required.")
                return None
            if self.get_user_by_email(email):
                st.error("Email already registered.")
                return None

            try:
                user_id = self.create_user(name=name, email=email, password=password)
                u = self.get_user_by_email(email)
                st.session_state["user"] = {"id": user_id, "email": u["email"], "name": u["name"]}
                return st.session_state["user"]
            except sqlite3.IntegrityError:
                st.error("Email already registered.")
                return None

        return None

