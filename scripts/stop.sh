#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

COMPONENT="${1:-all}"

stop_service() {
    local name="$1"
    local pidfile=".pids/${name}.pid"
    if [ -f "$pidfile" ]; then
        local pid
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            echo "Stopped $name (PID $pid)"
        else
            echo "$name not running (stale PID $pid)"
        fi
        rm -f "$pidfile"
    else
        echo "$name not running (no PID file)"
    fi
}

case "$COMPONENT" in
    all)
        stop_service beat
        stop_service worker
        stop_service api
        ;;
    api|worker|beat)
        stop_service "$COMPONENT"
        ;;
    *)
        echo "Usage: $0 [all|api|worker|beat]"
        exit 1
        ;;
esac
