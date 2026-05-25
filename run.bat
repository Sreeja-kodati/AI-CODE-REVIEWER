@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv venv
)
echo Installing dependencies...
venv\Scripts\python.exe -m pip install -r requirements.txt -q
echo Starting app at http://localhost:8501 ...
venv\Scripts\python.exe -m streamlit run app.py
pause
