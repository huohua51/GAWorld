#!/usr/bin/env bash
set -euo pipefail

SERVER_HOST="${SERVER_HOST:-10.72.74.13}"
SERVER_PORT="${SERVER_PORT:-10022}"
SERVER_USER="${SERVER_USER:-ft}"
APP_DIR="${APP_DIR:-/home/ft/GAWorld}"

tar \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='output' \
  -czf - . | ssh -p "$SERVER_PORT" "$SERVER_USER@$SERVER_HOST" "mkdir -p '$APP_DIR' && tar -xzf - -C '$APP_DIR' && chmod +x '$APP_DIR'/scripts/*.sh && systemctl --user restart gaworld-dashboard.service gaworld-agent-relay.service gaworld-test-loop.service"

echo "Deployed to http://$SERVER_HOST:8766/board"
