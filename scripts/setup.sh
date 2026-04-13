#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Ops-Knowledge Setup — venv + deps + migrate + init admin
# Prerequisites: Python 3.11+, GCC >= 10, Rust
# Usage:
#   ./scripts/setup.sh                                      # setup only
#   ./scripts/setup.sh --init admin admin@x.com Pass123!    # setup + create admin
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"
export PYTHONPATH="$PROJECT_DIR:${PYTHONPATH:-}"

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
pip install -r requirements.txt
pip install markitdown==0.1.5 --no-deps
pip install \
    beautifulsoup4 charset-normalizer defusedxml markdownify requests \
    "pdfminer.six>=20251230" "pdfplumber>=0.11.9" lxml "mammoth~=1.11.0" \
    python-pptx openpyxl -q
echo "Done"

# 3. .env
echo ""
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit it before running"
fi

# 4. migrate
echo ""
echo "Running migrations..."
alembic upgrade head

# 5. init admin (if --init flag provided)
if [ "${1:-}" = "--init" ]; then
    ADMIN_USER="${2:?Usage: $0 --init <username> <email> <password>}"
    ADMIN_EMAIL="${3:?Usage: $0 --init <username> <email> <password>}"
    ADMIN_PASS="${4:?Usage: $0 --init <username> <email> <password>}"

    python3 -c "
import asyncio
from app.system.service import InitService
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings

async def init():
    engine = create_async_engine(settings.DATABASE_URL)
    session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session() as db:
        svc = InitService(db)
        user = await svc.initialize('$ADMIN_USER', '$ADMIN_EMAIL', '$ADMIN_PASS')
        await db.commit()
        print(f'Admin created: {user.username} ({user.role.value})')
    await engine.dispose()

asyncio.run(init())
"
fi

echo ""
echo "=== Setup Complete ==="
echo "Start: bash scripts/start.sh api"
