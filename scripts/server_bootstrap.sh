#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/GAWorld}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8766}"
RELAY_PORT="${RELAY_PORT:-8877}"
TEST_BRANCH="${TEST_BRANCH:-tf}"
TEST_INTERVAL_SECONDS="${TEST_INTERVAL_SECONDS:-300}"

cd "$APP_DIR"

USE_VENV=1
if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv || USE_VENV=0
fi

if [ "$USE_VENV" = "1" ] && [ -f ".venv/bin/activate" ]; then
  . .venv/bin/activate
  python -m pip install --upgrade pip
  python -m pip install -r requirements-dev.txt
  RUN_PYTHON="$APP_DIR/.venv/bin/python"
else
  echo "[server_bootstrap] python venv unavailable; using user-site packages"
  "$PYTHON_BIN" -m pip install --user -r requirements-dev.txt
  RUN_PYTHON="$PYTHON_BIN"
fi

mkdir -p output/dashboard output/distributed output/test-logs

cat > "$APP_DIR/start_dashboard.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$APP_DIR"
if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi
exec "$RUN_PYTHON" dashboard_server.py --host 0.0.0.0 --port "$DASHBOARD_PORT"
EOF

cat > "$APP_DIR/start_agent_relay.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$APP_DIR"
if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi
exec "$RUN_PYTHON" distributed_comm_server.py --host 0.0.0.0 --port "$RELAY_PORT" --state-path output/distributed/relay_state.json
EOF

cat > "$APP_DIR/start_test_loop.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$APP_DIR"
if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi
export TEST_BRANCH="$TEST_BRANCH"
export TEST_INTERVAL_SECONDS="$TEST_INTERVAL_SECONDS"
export PYTHON_BIN="$RUN_PYTHON"
exec scripts/test_branch_loop.sh
EOF

chmod +x "$APP_DIR/start_dashboard.sh" "$APP_DIR/start_agent_relay.sh" "$APP_DIR/start_test_loop.sh"

if command -v systemctl >/dev/null 2>&1; then
  mkdir -p "$HOME/.config/systemd/user"
  cat > "$HOME/.config/systemd/user/gaworld-dashboard.service" <<EOF
[Unit]
Description=GAWorld dashboard and shared team board
After=network.target

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/start_dashboard.sh
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

  cat > "$HOME/.config/systemd/user/gaworld-agent-relay.service" <<EOF
[Unit]
Description=GAWorld remote agent relay
After=network.target

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/start_agent_relay.sh
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

  cat > "$HOME/.config/systemd/user/gaworld-test-loop.service" <<EOF
[Unit]
Description=GAWorld long-running test branch loop
After=network.target

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/start_test_loop.sh
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

  systemctl --user daemon-reload
  systemctl --user enable --now gaworld-dashboard.service gaworld-agent-relay.service gaworld-test-loop.service
else
  nohup "$APP_DIR/start_dashboard.sh" > output/dashboard/server.log 2>&1 &
  nohup "$APP_DIR/start_agent_relay.sh" > output/distributed/relay.log 2>&1 &
  nohup "$APP_DIR/start_test_loop.sh" > output/test-logs/test-loop.log 2>&1 &
fi

echo "Dashboard: http://$(hostname -I 2>/dev/null | awk '{print $1}'):$DASHBOARD_PORT/board"
echo "Console:   http://$(hostname -I 2>/dev/null | awk '{print $1}'):$DASHBOARD_PORT/dashboard"
echo "Relay:     http://$(hostname -I 2>/dev/null | awk '{print $1}'):$RELAY_PORT"
