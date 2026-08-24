#!/bin/bash

# Navigate to the script's directory
cd "$(dirname "$0")"

# Check if .venv directory exists
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/Scripts/activate || source .venv/bin/activate
else
    echo "Warning: .venv directory not found. Running with global python/streamlit..."
fi

rm -f pages/6_diagnostics.py

echo "Starting Enterprise HR AI Assistant (Streamlit)..."
streamlit run app.py
