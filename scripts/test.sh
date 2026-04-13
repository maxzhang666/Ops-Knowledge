#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

source .venv/bin/activate

MODE="${1:-all}"

case "$MODE" in
    all)
        echo "=== Running all tests ==="
        python -m pytest -v --tb=short
        ;;
    unit)
        echo "=== Running unit tests (no DB required) ==="
        python -m pytest tests/test_config.py tests/auth/test_schemas.py tests/model/test_schemas.py tests/knowledge/test_parser.py tests/knowledge/chunking/ tests/knowledge/test_quality_scorer.py tests/chat/test_context.py tests/chat/test_prompt.py tests/chat/test_citations.py -v --tb=short --noconftest
        ;;
    db)
        echo "=== Running DB-dependent tests ==="
        python -m pytest tests/auth/test_service.py tests/auth/test_api.py tests/department/ tests/system/ tests/model/test_service.py tests/model/test_api.py tests/knowledge/test_kb_crud.py tests/knowledge/test_document.py tests/chat/test_conversation.py tests/test_health.py tests/test_integration.py -v --tb=short
        ;;
    *)
        echo "Usage: $0 [all|unit|db]"
        echo "  all  — run all tests (requires PG + Redis + Milvus + MinIO)"
        echo "  unit — run unit tests only (no external services needed)"
        echo "  db   — run DB-dependent tests only (requires PG + Redis)"
        exit 1
        ;;
esac
