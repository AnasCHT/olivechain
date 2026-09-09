#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_versions

[[ -s "$FABRIC_NETWORK_DIR/channel-artifacts/$CHANNEL_NAME.block" ]] || {
  echo "Generate the channel block first" >&2; exit 1;
}
mkdir -p "$FABRIC_NETWORK_DIR/public-artifacts/outbox"
tar -C "$FABRIC_NETWORK_DIR" -czf \
  "$FABRIC_NETWORK_DIR/public-artifacts/outbox/olivechain-consortium.tar.gz" \
  public-artifacts/current channel-artifacts/"$CHANNEL_NAME.block"
echo "Wrote public-artifacts/outbox/olivechain-consortium.tar.gz"
