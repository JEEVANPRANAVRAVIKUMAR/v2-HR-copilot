Set-Location $PSScriptRoot

if (Test-Path ".venv\Scripts\Activate.ps1") {
    Write-Host "Activating virtual environment..." -ForegroundColor Green
    & .venv\Scripts\Activate.ps1
} else {
    Write-Host "Warning: .venv virtual environment activation script not found. Running with global python/streamlit..." -ForegroundColor Yellow
}

# Clean up duplicate page to avoid Streamlit URL collision
if (Test-Path "pages\6_diagnostics.py") {
    Remove-Item "pages\6_diagnostics.py" -Force
}

Write-Host "Starting Enterprise HR AI Assistant (Streamlit)..." -ForegroundColor Cyan
streamlit run app.py
