# AI Code Reviewer - one-click launcher (PowerShell)
Set-Location $PSScriptRoot

if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    python -m venv venv
}

Write-Host "Installing dependencies (if needed)..."
& ".\venv\Scripts\python.exe" -m pip install -r requirements.txt -q

Write-Host "Starting app at http://localhost:8501 ..."
& ".\venv\Scripts\python.exe" -m streamlit run app.py
