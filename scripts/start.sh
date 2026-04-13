#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Ops-Knowledge Backend Start (Bare Metal)
#
# Designed for supervisor: each component runs in FOREGROUND mode.
# supervisor handles daemonization, restart, and log routing.
#
# Usage:
#   ./scripts/start.sh api      # foreground uvicorn
#   ./scripts/start.sh worker   # foreground celery worker
#   ./scripts/start.sh beat     # foreground celery beat
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

source .venv/bin/activate

COMPONENT="${1:?Usage: $0 [api|worker|beat]}"

case "$COMPONENT" in
    api)
        exec uvicorn app.main:app \
            --host 0.0.0.0 \
            --port 8000 \
            --workers 2 \
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
