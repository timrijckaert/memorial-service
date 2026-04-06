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
    echo "Install it with: brew install tesseract tesseract-lang"
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

# Run the merge script
"$VENV_DIR/bin/python" "$SCRIPT_DIR/src/merge.py"
