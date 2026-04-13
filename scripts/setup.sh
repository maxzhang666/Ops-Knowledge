#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Ops-Knowledge Backend Setup (Bare Metal)
#
# Prerequisites on target server:
#   - Python 3.11+
#   - PostgreSQL 16+
#   - Redis 7+
#   - Milvus Standalone (with etcd) — or skip if not testing retrieval
#   - MinIO — or skip if not testing document upload
#
# Usage:
#   chmod +x scripts/setup.sh
#   ./scripts/setup.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=== Ops-Knowledge Setup ==="
echo "Project dir: $PROJECT_DIR"

# ---------- 1. Python venv ----------
echo ""
echo "[1/6] Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "  Created .venv"
else
    echo "  .venv already exists"
fi

source .venv/bin/activate
echo "  Python: $(python3 --version)"

# ---------- 2. Dependencies ----------
echo ""
echo "[2/6] Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  Done ($(pip list --format=columns | wc -l) packages)"

# ---------- 3. Environment file ----------
echo ""
echo "[3/6] Environment file..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "  Created .env from .env.example"
        echo "  *** EDIT .env to match your server configuration ***"
    else
        cat > .env << 'ENVEOF'
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://opsknowledge:opsknowledge@localhost:5432/ops_knowledge

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT (CHANGE THIS in production)
JWT_SECRET_KEY=change-this-to-a-random-secret-key-in-production

# Milvus (optional, skip if not testing retrieval)
MILVUS_URI=http://localhost:19530

# MinIO (optional, skip if not testing document upload)
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=ops-knowledge-docs
MINIO_SECURE=false
ENVEOF
        echo "  Created .env with defaults"
        echo "  *** EDIT .env to match your server configuration ***"
    fi
else
    echo "  .env already exists"
fi

# ---------- 4. PostgreSQL setup ----------
echo ""
echo "[4/6] PostgreSQL databases..."

# Extract PG connection info from DATABASE_URL
DB_URL=$(grep '^DATABASE_URL=' .env | cut -d= -f2-)
# Parse: postgresql+asyncpg://user:pass@host:port/dbname
PG_USER=$(echo "$DB_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
PG_PASS=$(echo "$DB_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
PG_HOST=$(echo "$DB_URL" | sed -n 's|.*@\([^:]*\):.*|\1|p')
PG_PORT=$(echo "$DB_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
PG_DB=$(echo "$DB_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')

export PGPASSWORD="$PG_PASS"

# Create user if not exists
psql -h "$PG_HOST" -p "$PG_PORT" -U postgres -tc \
    "SELECT 1 FROM pg_roles WHERE rolname='$PG_USER'" 2>/dev/null | grep -q 1 || {
    psql -h "$PG_HOST" -p "$PG_PORT" -U postgres -c \
        "CREATE USER $PG_USER WITH PASSWORD '$PG_PASS';" 2>/dev/null || true
    echo "  Created PG user: $PG_USER"
}

# Create main database
psql -h "$PG_HOST" -p "$PG_PORT" -U postgres -tc \
    "SELECT 1 FROM pg_database WHERE datname='$PG_DB'" 2>/dev/null | grep -q 1 || {
    psql -h "$PG_HOST" -p "$PG_PORT" -U postgres -c \
        "CREATE DATABASE $PG_DB OWNER $PG_USER;" 2>/dev/null
    echo "  Created database: $PG_DB"
}

# Create test database
psql -h "$PG_HOST" -p "$PG_PORT" -U postgres -tc \
    "SELECT 1 FROM pg_database WHERE datname='${PG_DB}_test'" 2>/dev/null | grep -q 1 || {
    psql -h "$PG_HOST" -p "$PG_PORT" -U postgres -c \
        "CREATE DATABASE ${PG_DB}_test OWNER $PG_USER;" 2>/dev/null
    echo "  Created test database: ${PG_DB}_test"
}

unset PGPASSWORD
echo "  PG databases ready"

# ---------- 5. Alembic migrations ----------
echo ""
echo "[5/6] Running database migrations..."
alembic upgrade head
echo "  Migrations applied"

# ---------- 6. Verify services ----------
echo ""
echo "[6/6] Service connectivity check..."

python3 -c "
import sys

# PostgreSQL
try:
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    async def check_pg():
        engine = create_async_engine('$DB_URL')
        async with engine.connect() as conn:
            await conn.execute(text('SELECT 1'))
        await engine.dispose()
    asyncio.run(check_pg())
    print('  PostgreSQL: OK')
except Exception as e:
    print(f'  PostgreSQL: FAILED ({e})')

# Redis
try:
    import redis
    r = redis.from_url('$(grep "^REDIS_URL=" .env | cut -d= -f2-)')
    r.ping()
    r.close()
    print('  Redis: OK')
except Exception as e:
    print(f'  Redis: FAILED ({e})')

# Milvus
try:
    from pymilvus import MilvusClient
    client = MilvusClient(uri='$(grep "^MILVUS_URI=" .env | cut -d= -f2- || echo "http://localhost:19530")')
    client.list_collections()
    client.close()
    print('  Milvus: OK')
except Exception as e:
    print(f'  Milvus: SKIP ({e})')

# MinIO
try:
    import boto3
    from botocore.config import Config
    endpoint = '$(grep "^MINIO_ENDPOINT=" .env | cut -d= -f2- || echo "localhost:9000")'
    client = boto3.client('s3',
        endpoint_url=f'http://{endpoint}',
        aws_access_key_id='$(grep "^MINIO_ACCESS_KEY=" .env | cut -d= -f2- || echo "minioadmin")',
        aws_secret_access_key='$(grep "^MINIO_SECRET_KEY=" .env | cut -d= -f2- || echo "minioadmin")',
        config=Config(signature_version='s3v4'), region_name='us-east-1')
    client.list_buckets()
    print('  MinIO: OK')
except Exception as e:
    print(f'  MinIO: SKIP ({e})')
"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env if needed"
echo "  2. Run tests:    ./scripts/test.sh"
echo "  3. Start server: ./scripts/start.sh"
