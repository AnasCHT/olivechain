#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT:-$HOME/olivechain-main}"
ENV_FILE="${OLIVECHAIN_FABRIC_APP_ENV:-$PROJECT/fabric-app.env}"

[[ -f "$ENV_FILE" ]] || {
  echo "Missing $ENV_FILE; copy fabric-app.env.example to fabric-app.env and edit it." >&2
  exit 1
}

set -a
source "$ENV_FILE"
set +a

PYTHON_BIN="${OLIVECHAIN_PYTHON:-$(command -v python3 || true)}"
[[ -n "$PYTHON_BIN" && -x "$PYTHON_BIN" ]] || {
  echo "Python not found. Set OLIVECHAIN_PYTHON to the interpreter that has the project requirements." >&2
  exit 1
}

BIND="${OLIVECHAIN_APP_BIND:-0.0.0.0}"
PORT="${OLIVECHAIN_APP_PORT:-8000}"
LAN_IP="${OLIVECHAIN_LAN_IP:-}"

if [[ -z "$LAN_IP" && -f "$PROJECT/fabric-network/machines/machine1/.env" ]]; then
  LAN_IP="$(sed -n 's/^M1_IP=//p' "$PROJECT/fabric-network/machines/machine1/.env" | tail -n1 | tr -d "'\"")"
fi
if [[ -z "$LAN_IP" ]] && command -v ipconfig >/dev/null 2>&1; then
  LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
fi
if [[ -z "$LAN_IP" ]] && command -v hostname >/dev/null 2>&1; then
  LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
fi

cd "$PROJECT"
echo "Starting OliveChain 1.0.0"
echo "  Python:  $PYTHON_BIN"
echo "  Backend: ${OLIVECHAIN_LEDGER_BACKEND:-local}"
echo "  Local:   http://127.0.0.1:$PORT"
if [[ "$BIND" == "0.0.0.0" && -n "$LAN_IP" ]]; then
  echo "  LAN:     http://$LAN_IP:$PORT"
  echo "  Other LAN devices can use the LAN URL while this process is running."
fi

exec "$PYTHON_BIN" -m uvicorn serve:app \
  --host "$BIND" \
  --port "$PORT"
