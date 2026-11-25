#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "============================================================"
echo " SWOOZ PITWALL — STEAM DECK / LINUX LAUNCHER"
echo " Open on Any Phone / Tablet / Foldable: http://${IP:-127.0.0.1}:8765"
echo "============================================================"
exec python3 server.py --web-host 0.0.0.0 --telemetry-ip 0.0.0.0 "$@"
