#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_versions
load_machine "${1:?usage: start-node.sh machine1}"
assert_no_example_secrets
require_command docker

[[ -d "$CRYPTO_DIR/peerOrganizations/$PEER_ORG_DOMAIN/peers/$PEER_FQDN/msp" ]] || {
  echo "Missing peer identity; run enroll-machine.sh" >&2; exit 1;
}
if [[ "$HAS_ORDERER" == "true" ]]; then
  [[ -d "$CRYPTO_DIR/ordererOrganizations/$ORDERER_ORG_DOMAIN/orderers/$ORDERER_FQDN/msp" ]] || {
    echo "Missing orderer identity; run enroll-machine.sh" >&2; exit 1;
  }
  for org in ordererorg1 ordererorg2 ordererorg3; do
    [[ -s "$FABRIC_NETWORK_DIR/public-artifacts/current/$org/tlsca.pem" ]] || {
      echo "Missing consortium TLS roots; run import-consortium.sh" >&2; exit 1;
    }
  done
fi
mkdir -p "$RUNTIME_DIR/production/peer" "$RUNTIME_DIR/production/couchdb" "$RUNTIME_DIR/production/orderer"
compose compose-node.yaml up -d
compose compose-node.yaml ps
