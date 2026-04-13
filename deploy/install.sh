#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Ops-Knowledge Supervisor Install Helper
#
# Usage:
#   sudo ./deploy/install.sh /opt/ops-knowledge appuser
#
# This generates the actual supervisor conf with resolved paths,
# installs it, and starts the services.
# =============================================================================

PROJECT_DIR="${1:?Usage: $0 <project_dir> <run_user>}"
RUN_USER="${2:?Usage: $0 <project_dir> <run_user>}"

if [ ! -f "$PROJECT_DIR/scripts/start.sh" ]; then
    echo "Error: $PROJECT_DIR does not look like an Ops-Knowledge project"
    exit 1
fi

echo "=== Installing Ops-Knowledge supervisor config ==="
echo "  Project: $PROJECT_DIR"
echo "  User:    $RUN_USER"

# Create log directory
mkdir -p "$PROJECT_DIR/logs"
chown "$RUN_USER:$RUN_USER" "$PROJECT_DIR/logs"

# Generate resolved supervisor config
CONF_FILE="/etc/supervisor/conf.d/ops-knowledge.conf"
cat > "$CONF_FILE" << EOF
[group:ops-knowledge]
programs=api,worker,beat

[program:api]
command=${PROJECT_DIR}/scripts/start.sh api
directory=${PROJECT_DIR}
user=${RUN_USER}
autostart=true
autorestart=true
startsecs=5
startretries=3
stopwaitsecs=30
stopasgroup=true
killasgroup=true
stdout_logfile=${PROJECT_DIR}/logs/api.log
stderr_logfile=${PROJECT_DIR}/logs/api-error.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=5

[program:worker]
command=${PROJECT_DIR}/scripts/start.sh worker
directory=${PROJECT_DIR}
user=${RUN_USER}
autostart=true
autorestart=true
startsecs=10
startretries=3
stopwaitsecs=60
stopasgroup=true
killasgroup=true
stdout_logfile=${PROJECT_DIR}/logs/worker.log
stderr_logfile=${PROJECT_DIR}/logs/worker-error.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=5

[program:beat]
command=${PROJECT_DIR}/scripts/start.sh beat
directory=${PROJECT_DIR}
user=${RUN_USER}
autostart=true
autorestart=true
startsecs=5
startretries=3
stopwaitsecs=10
stopasgroup=true
killasgroup=true
stdout_logfile=${PROJECT_DIR}/logs/beat.log
stderr_logfile=${PROJECT_DIR}/logs/beat-error.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
EOF

echo "  Config written to $CONF_FILE"

# Reload supervisor
supervisorctl reread
supervisorctl update
supervisorctl start ops-knowledge:*

echo ""
echo "=== Done ==="
echo "  Status: sudo supervisorctl status ops-knowledge:*"
echo "  Logs:   tail -f $PROJECT_DIR/logs/api.log"
