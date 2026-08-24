@echo off
cd /d "%~dp0"

if exist .venv\Scripts\activate.bat (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
) else (
    echo Warning: .venv virtual environment activation script not found. Running with global python/streamlit...
)

if exist pages\6_diagnostics.py del /f /q pages\6_diagnostics.py

echo Starting Enterprise HR AI Assistant (Streamlit)...
streamlit run app.py
