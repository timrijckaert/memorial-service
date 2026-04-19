#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# Store MLX models inside the project (portable — copy the whole folder to another Mac)
export HF_HUB_CACHE="$SCRIPT_DIR/models"

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

# Create venv if it doesn't exist or is from another machine
if [ ! -d "$VENV_DIR" ] || ! "$VENV_DIR/bin/python" --version &>/dev/null; then
    rm -rf "$VENV_DIR"
    echo "Setting up virtual environment..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
    echo "Setup complete."
    echo ""
fi

# Pre-download MLX models if not cached
echo "Checking MLX models..."
"$VENV_DIR/bin/python" -c "
from mlx_lm import load as lm_load
from mlx_vlm import load as vlm_load
print('  Checking text model...')
lm_load('mlx-community/gemma-3-4b-it-4bit')
print('  Text model ready.')
print('  Checking vision model...')
vlm_load('mlx-community/Qwen2.5-VL-3B-Instruct-4bit')
print('  Vision model ready.')
"
echo ""

# Run the pipeline
cd "$SCRIPT_DIR"
"$VENV_DIR/bin/python" -m src.main "$@"
