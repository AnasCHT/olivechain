#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_versions
require_command configtxgen

for org in farmer maker courier recycler ordererorg1 ordererorg2 ordererorg3; do
  [[ -d "$FABRIC_NETWORK_DIR/public-artifacts/current/$org/msp" ]] || {
    echo "Missing public MSP for $org; run import-public.sh" >&2; exit 1;
  }
done

mkdir -p "$FABRIC_NETWORK_DIR/channel-artifacts"
(
  cd "$FABRIC_NETWORK_DIR/configtx"
  FABRIC_CFG_PATH="$FABRIC_NETWORK_DIR/configtx" configtxgen \
    -profile OliveChannel \
    -channelID "$CHANNEL_NAME" \
    -outputBlock "$FABRIC_NETWORK_DIR/channel-artifacts/$CHANNEL_NAME.block"
)

echo "Generated $FABRIC_NETWORK_DIR/channel-artifacts/$CHANNEL_NAME.block"
