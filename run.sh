#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# Check Python 3 is available
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required but not found."
    echo "Install it from https://www.python.org/downloads/ or via Homebrew: brew install python3"
    exit 1
fi

# Check Tesseract is available
if ! command -v tesseract &>/dev/null; then
    echo "Error: tesseract is required but not found."
    echo "Install it with: brew install tesseract"
    exit 1
fi

# Download Dutch language pack if missing
TESSDATA_DIR="$(dirname "$(command -v tesseract)")/../share/tessdata"
if [ ! -f "$TESSDATA_DIR/nld.traineddata" ]; then
    echo "Downloading Dutch language pack for Tesseract..."
    curl -sL -o "$TESSDATA_DIR/nld.traineddata" \
        https://github.com/tesseract-ocr/tessdata_best/raw/main/nld.traineddata
    echo "Dutch language pack installed."
    echo ""
fi

# Check config.json exists
if [ ! -f "$SCRIPT_DIR/config.json" ]; then
    echo "Error: config.json not found."
    echo "Create it with your Gemini API key:"
    echo '  {"gemini_api_key": "your-api-key-here"}'
    exit 1
fi

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Setting up virtual environment..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
    echo "Setup complete."
    echo ""
fi

# Run the pipeline
"$VENV_DIR/bin/python" "$SCRIPT_DIR/src/main.py" "$@"
