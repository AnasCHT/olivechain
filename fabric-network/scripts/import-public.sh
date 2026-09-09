#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_versions

inbox="$FABRIC_NETWORK_DIR/public-artifacts/inbox"
current="$FABRIC_NETWORK_DIR/public-artifacts/current"
rm -rf "$current"
mkdir -p "$current"

for machine in machine1 machine2 machine3 machine4; do
  archive="$inbox/$machine-public.tar.gz"
  [[ -s "$archive" ]] || { echo "Missing $archive" >&2; exit 1; }
  tar -xzf "$archive" -C "$current"
done

for org in farmer maker courier recycler ordererorg1 ordererorg2 ordererorg3; do
  [[ -d "$current/$org/msp" ]] || { echo "Missing public MSP for $org" >&2; exit 1; }
done
for org in ordererorg1 ordererorg2 ordererorg3; do
  [[ -s "$current/$org/orderer-tls-server.crt" ]] || { echo "Missing TLS consenter cert for $org" >&2; exit 1; }
done

echo "Imported all seven public MSPs into $current."
