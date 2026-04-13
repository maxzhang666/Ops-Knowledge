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

# 2. deps
echo "Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt
echo "Done"

# 3. .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit it to match your server"
fi

echo ""
echo "=== Setup Complete ==="
echo "Next: edit .env → alembic upgrade head → ./scripts/test.sh unit"
