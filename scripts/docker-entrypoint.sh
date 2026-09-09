#!/bin/sh
set -e

# Seed the demo pilot on first boot only (volumes empty).
if [ ! -f data/ledger.jsonl ]; then
  echo "No ledger found - seeding demo pilot data..."
  python demo/run_pilot.py
fi

# --proxy-headers restores client IPs behind Caddy so rate limits work per client.
exec python -m uvicorn serve:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'
