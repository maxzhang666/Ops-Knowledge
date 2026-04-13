#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Load Rust if available
[ -f "$HOME/.cargo/env" ] && source "$HOME/.cargo/env"

source .venv/bin/activate

# Run migrations before start
echo "Running migrations..."
alembic upgrade head

COMPONENT="${1:?Usage: $0 [api|worker|beat]}"

case "$COMPONENT" in
    api)
        exec uvicorn app.main:app \
            --host 0.0.0.0 \
            --port 8200 \
            --reload \
            --log-level info
        ;;
    worker)
        exec celery -A app.core.celery worker \
            --loglevel=info \
            --concurrency=4 \
            -Q default,document,embedding
        ;;
    beat)
        exec celery -A app.core.celery beat \
            --loglevel=info
        ;;
    *)
        echo "Usage: $0 [api|worker|beat]"
        exit 1
        ;;
esac
