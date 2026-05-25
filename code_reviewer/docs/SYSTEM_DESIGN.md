# System Design — AI-Powered Automated Code Reviewer

## 1) Problem Statement
Developers need fast, consistent feedback on code changes: bugs, security issues, performance problems, and code-quality concerns. Traditional tools (linters, SAST) are useful but limited in expressiveness and explanation quality. This project combines **static analysis** with an **AI review engine** to provide actionable, structured reviews.

## 2) Objectives
- Review code from multiple input methods:
  - Paste snippets
  - Upload one or more code files
  - Upload a zip project
  - Connect to a GitHub repository
  - (Optional/best-effort) review pull request files/diffs
- Detect issues across:
  - Syntax / static correctness
  - Logical errors (heuristic-based + AI reasoning)
  - Code smells + maintainability (lint/complexity + AI)
  - Performance (complexity + AI)
  - Duplicate code (heuristic chunk similarity + AI)
  - Security vulnerabilities (rule-based + SAST hooks like bandit where possible)
- Provide:
  - Severity (Critical/High/Medium/Low)
  - Explanation
  - Suggested fixes
  - Improved code (best-effort; AI guardrails to avoid unsafe hallucinations)
- Persist:
  - Users
  - Review history
  - Review results and generated reports
- Present a production-ready UX using Streamlit.

## 3) Functional Requirements
### Input & Review
- Accept code via:
  - Text area (paste)
  - File upload (single/multiple)
  - Zip upload
  - GitHub repo selection (API fetch)
  - PR review support (best-effort; optional)
- Support language hints + auto-detection fallback.
- Run a review pipeline that includes:
  1. Code parsing + normalization
  2. Static analysis aggregation
  3. Security scanning
  4. AI review generation (structured output)
  5. Scoring & report generation

### UI Features
- Login/Register
- Sidebar navigation (Review, History/Profile)
- Review scores and issue lists
- Save report + download PDF
- Dark mode
- Search in history

### Backend Features
- Structured and consistent outputs:
  - Unified issue schema
  - Review result JSON persisted to SQLite
- Robust handling:
  - Large files (chunking)
  - Unsupported languages (still run security heuristics + AI)
  - Timeouts and model errors

## 4) Non-Functional Requirements
- **Security**:
  - Never store plaintext passwords
  - Parameterized SQL queries
  - Avoid SSRF in GitHub fetching
  - Token handling server-side only
- **Reliability**:
  - Deterministic failures with clear UI messages
  - Graceful degradation when AI/static tools unavailable
- **Performance**:
  - Chunking and incremental analysis
  - Caching analysis where safe
- **Maintainability**:
  - Clean architecture modules
  - Extensive logging
  - Unit tests for key utilities
- **Portability**:
  - Dockerized deployment

## 5) User Flow
1. User logs in.
2. User selects an input method:
   - Paste code, upload files/zip, or connect GitHub.
3. User selects language (or auto-detect).
4. Click “Run Review”.
5. Backend pipeline runs:
   - Parse → static analysis → security scan → AI review → scoring → persistence → report generation.
6. UI displays scores and categorized issues.
7. User can save and download a PDF report.

## 6) System Architecture
### High-level components
- **Streamlit UI**: gathers inputs; displays results; triggers backend pipeline.
- **Code Processing Layer**:
  - parsing, cleaning, language detection, chunking
- **Static Analysis Engine**:
  - linting + complexity + security hooks
- **AI Review Engine**:
  - LLM/huggingface instruction generation
- **Security Checker**:
  - rule-based heuristics + optional bandit
- **Database Layer**:
  - SQLite persistence
- **Report Generator**:
  - HTML/Markdown and PDF rendering

### Architecture diagram (text)
User
↓
Streamlit UI
↓
Code Processing Layer
↓
Static Analysis Engine
↓
AI Review Engine
↓
Security Checker
↓
Database
↓
Report Generator
↓
Streamlit UI (render + download)

## 7) Data Model (conceptual)
- Users
- Reviews (one per run; includes JSON result)
- Report artifacts (files on disk keyed by review id)

## 8) Guardrails for AI Output
- Always base AI issues on collected static/security analysis.
- If “improved code” cannot be confidently produced, provide:
  - targeted diffs/pseudo-patches
  - or “suggested code pattern” rather than a complete replacement.
- Prevent leaking secrets from prompts (strip secrets-like patterns before sending to AI).

## 9) Threat Model (summary)
- Prompt injection in code content → mitigated by:
  - sanitation before LLM calls
  - strict system instructions
- SQL injection → mitigated with parameterized queries
- Credential leakage → password hashing + log redaction
- Unsafe file operations on uploads → extract zip into sandboxed temp dir and restrict paths

## 10) Observability
- Structured logs with correlation id per review.
- Capture static tool stderr/stdout (bounded), and store only sanitized snippets.


