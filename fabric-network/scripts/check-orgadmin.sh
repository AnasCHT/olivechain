#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

MACHINE_ARG="${1:?usage: check-orgadmin.sh machine1|machine2|machine3|machine4}"

load_versions
load_machine "$MACHINE_ARG"
source "$FABRIC_NETWORK_DIR/chaincode/chaincode.env"

peer_org="$CRYPTO_DIR/peerOrganizations/$PEER_ORG_DOMAIN"
admin_msp="$peer_org/users/Admin@$PEER_ORG_DOMAIN/msp"

export CORE_PEER_LOCALMSPID="$PEER_MSP_ID"
export CORE_PEER_MSPCONFIGPATH="$admin_msp"
export CORE_PEER_ADDRESS=localhost:7051
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_TLS_ROOTCERT_FILE="$peer_org/peers/$PEER_FQDN/tls/ca.crt"

echo "Checking $MACHINE / $PEER_MSP_ID..."

peer chaincode query \
  --channelID "$CHANNEL_NAME" \
  --name "$CC_NAME" \
  --ctor '{"Args":["WhoAmI"]}'
