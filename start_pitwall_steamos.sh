#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PY=""
if command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
else
  echo "ERROR: Python 3 is not installed or not in PATH on this system."
  echo "On SteamOS Desktop Mode, install python or use an AppImage/distrobox python3."
  exit 1
fi

IP=$("$PY" -c '
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("10.255.255.255", 1))
    print(s.getsockname()[0])
    s.close()
except Exception:
    print("127.0.0.1")
' 2>/dev/null || echo "127.0.0.1")

echo "============================================================"
echo " SWOOZ PITWALL — STEAM DECK / LINUX LAUNCHER"
echo " Open on Any Phone / Tablet / Foldable: http://${IP:-127.0.0.1}:8765"
echo "============================================================"

exec "$PY" server.py --web-host 0.0.0.0 --telemetry-ip 0.0.0.0 "$@"