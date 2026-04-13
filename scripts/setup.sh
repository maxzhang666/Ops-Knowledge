#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Ops-Knowledge Setup — Python venv + dependencies only
# Usage: ./scripts/setup.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=== Ops-Knowledge Setup ==="

# Check compilers
GCC_MAJOR=$(gcc -dumpversion 2>/dev/null | cut -d. -f1 || echo "0")
[ "$GCC_MAJOR" -lt 10 ] && echo "ERROR: GCC >= 10 required" && exit 1
command -v rustc &>/dev/null || { echo "ERROR: Rust not found"; exit 1; }

# venv
[ ! -d ".venv" ] && python3 -m venv .venv && echo "Created .venv"
source .venv/bin/activate
echo "Python: $(python3 --version), GCC: $(gcc -dumpversion), Rust: $(rustc --version | cut -d' ' -f2)"

# deps
echo "Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt
pip install markitdown==0.1.5 --no-deps
pip install beautifulsoup4 charset-normalizer defusedxml markdownify requests \
    "pdfminer.six>=20251230" "pdfplumber>=0.11.9" lxml "mammoth~=1.11.0" \
    python-pptx openpyxl -q

# .env
[ ! -f ".env" ] && cp .env.example .env && echo "Created .env — edit it before starting"

echo "=== Done. Next: edit .env → supervisorctl start ops-knowledge:api ==="
