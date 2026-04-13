#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Ops-Knowledge Setup — venv + deps + migrate + init admin
# Prerequisites: Python 3.11+, GCC >= 10, Rust
# Usage: ./scripts/setup.sh
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
pip install -r requirements.txt

# markitdown: --no-deps to skip magika→onnxruntime, then install real deps
pip install markitdown==0.1.5 --no-deps
pip install \
    beautifulsoup4 \
    charset-normalizer \
    defusedxml \
    markdownify \
    requests \
    "pdfminer.six>=20251230" \
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

# 4. migrate
echo ""
echo "Running migrations..."
alembic upgrade head

# 5. init admin (if first time)
echo ""
NEEDS_INIT=$(python3 -c "
import asyncio
from app.core.config import settings
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        result = await conn.execute(text('SELECT COUNT(*) FROM users'))
        count = result.scalar()
    await engine.dispose()
    return count == 0

print(asyncio.run(check()))
" 2>/dev/null || echo "False")

if [ "$NEEDS_INIT" = "True" ]; then
    echo "=== Create Admin Account ==="
    read -p "  Username: " ADMIN_USER
    read -p "  Email: " ADMIN_EMAIL
    read -s -p "  Password: " ADMIN_PASS
    echo ""

    python3 -c "
import asyncio, sys
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
        print(f'  Admin created: {user.username} ({user.role.value})')
    await engine.dispose()

asyncio.run(init())
" || echo "  ERROR: Failed to create admin"
else
    echo "Admin account already exists, skipping init"
fi

echo ""
echo "=== Setup Complete ==="
echo "Start: bash scripts/start.sh api"
