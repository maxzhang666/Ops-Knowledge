#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Ops-Knowledge Setup — Python venv + dependencies
# Prerequisites: Python 3.11+, GCC >= 10, Rust (for tiktoken)
# Usage: ./scripts/setup.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=== Ops-Knowledge Setup ==="

# Pre-flight: check compilers
echo ""
echo "Checking compilers..."

GCC_VER=$(gcc -dumpversion 2>/dev/null || echo "0")
GCC_MAJOR=$(echo "$GCC_VER" | cut -d. -f1)
if [ "$GCC_MAJOR" -lt 10 ]; then
    echo "ERROR: GCC >= 10 required (found: $GCC_VER)"
    exit 1
fi
echo "  GCC: $GCC_VER"

if ! command -v rustc &>/dev/null; then
    echo "ERROR: Rust compiler not found (required by tiktoken)"
    echo "Fix:   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    exit 1
fi
echo "  Rust: $(rustc --version)"

# 1. venv
echo ""
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "Created .venv"
else
    echo ".venv exists"
fi

source .venv/bin/activate
echo "Python: $(python3 --version)"

# 2. deps
echo ""
echo "Installing dependencies..."
pip install --upgrade pip -q

# Main deps (markitdown excluded from requirements.txt)
pip install -r requirements.txt

# markitdown: install --no-deps to skip magika→onnxruntime (no wheel for Amazon Linux 2)
# then install ALL its real runtime deps manually
# Source: markitdown 0.1.5 METADATA Requires-Dist (minus magika)
pip install markitdown==0.1.5 --no-deps
pip install \
    beautifulsoup4 \
    charset-normalizer \
    defusedxml \
    markdownify \
    requests \
    pdfminer.six">=20251230" \
    "pdfplumber>=0.11.9" \
    lxml \
    "mammoth~=1.11.0" \
    python-pptx \
    openpyxl

echo "Done"

# 3. .env
echo ""
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit it to match your server"
fi

# 4. verify markitdown import
echo ""
echo "Verifying markitdown..."
python3 -c "from markitdown import MarkItDown; print('  markitdown OK')" 2>&1 || echo "  WARNING: markitdown import failed"

echo ""
echo "=== Setup Complete ==="
echo "Next: edit .env → bash scripts/start.sh api"
