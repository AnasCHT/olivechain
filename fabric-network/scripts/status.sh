#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_versions
load_machine "${1:?usage: status.sh machine1}"
require_command peer

compose compose-node.yaml ps
peer_org="$CRYPTO_DIR/peerOrganizations/$PEER_ORG_DOMAIN"
export CORE_PEER_LOCALMSPID="$PEER_MSP_ID"
export CORE_PEER_MSPCONFIGPATH="$peer_org/users/Admin@$PEER_ORG_DOMAIN/msp"
export CORE_PEER_ADDRESS=localhost:7051
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_TLS_ROOTCERT_FILE="$peer_org/peers/$PEER_FQDN/tls/ca.crt"

echo
peer channel list
echo
peer channel getinfo -c "$CHANNEL_NAME"

if [[ "$HAS_ORDERER" == "true" ]]; then
  require_command osnadmin
  osn_tls="$CRYPTO_DIR/ordererOrganizations/$ORDERER_ORG_DOMAIN/users/osnadmin@$ORDERER_ORG_DOMAIN/tls"
  echo
  osnadmin channel list -o localhost:7053 \
    --ca-file "$osn_tls/ca.crt" \
    --client-cert "$osn_tls/client.crt" \
    --client-key "$osn_tls/client.key"
fi
