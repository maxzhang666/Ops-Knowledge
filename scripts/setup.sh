#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Ops-Knowledge Setup — Python venv + dependencies only
# Prerequisites: Python 3.11+ on the server
# Usage: ./scripts/setup.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=== Ops-Knowledge Setup ==="

# 1. venv
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "Created .venv"
else
    echo ".venv exists"
fi

source .venv/bin/activate
echo "Python: $(python3 --version)"

# 2. deps (markitdown installed separately to skip magika/onnxruntime)
echo "Installing dependencies..."
pip install --upgrade pip -q

# Install markitdown without its deps first, then install the rest
pip install markitdown==0.1.5 --no-deps -q

# Install all other deps (markitdown line will be skipped since already installed)
pip install -r requirements.txt --ignore-installed markitdown -q 2>/dev/null || \
    pip install -r requirements.txt -q

echo "Done"

# 3. .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit it to match your server"
fi

echo ""
echo "=== Setup Complete ==="
echo "Next: edit .env → alembic upgrade head → ./scripts/test.sh unit"
