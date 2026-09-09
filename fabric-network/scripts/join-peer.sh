#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_versions
load_machine "${1:?usage: join-peer.sh machine1}"
require_command peer

block="$FABRIC_NETWORK_DIR/channel-artifacts/$CHANNEL_NAME.block"
peer_org="$CRYPTO_DIR/peerOrganizations/$PEER_ORG_DOMAIN"
export CORE_PEER_LOCALMSPID="$PEER_MSP_ID"
export CORE_PEER_MSPCONFIGPATH="$peer_org/users/Admin@$PEER_ORG_DOMAIN/msp"
export CORE_PEER_ADDRESS=localhost:7051
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_TLS_ROOTCERT_FILE="$peer_org/peers/$PEER_FQDN/tls/ca.crt"

[[ -s "$block" ]] || { echo "Missing channel block" >&2; exit 1; }
set +e
output="$(peer channel join -b "$block" 2>&1)"
rc=$?
set -e
if (( rc != 0 )) && ! grep -qiE 'exists|already' <<<"$output"; then
  echo "$output" >&2
  exit "$rc"
fi
echo "$output"
peer channel getinfo -c "$CHANNEL_NAME"
