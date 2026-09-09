#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_versions
load_machine "${1:?usage: export-public.sh machine1}"

outbox="$FABRIC_NETWORK_DIR/public-artifacts/outbox"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir -p "$outbox" "$stage/$PEER_ORG_SLUG"

peer_org="$CRYPTO_DIR/peerOrganizations/$PEER_ORG_DOMAIN"
[[ -d "$peer_org/msp" ]] || { echo "Run enroll-machine.sh first" >&2; exit 1; }
cp -a "$peer_org/msp" "$stage/$PEER_ORG_SLUG/msp"
cp "$peer_org/peers/$PEER_FQDN/tls/ca.crt" "$stage/$PEER_ORG_SLUG/tlsca.pem"

if [[ "$HAS_ORDERER" == "true" ]]; then
  orderer_org="$CRYPTO_DIR/ordererOrganizations/$ORDERER_ORG_DOMAIN"
  mkdir -p "$stage/$ORDERER_ORG_SLUG"
  cp -a "$orderer_org/msp" "$stage/$ORDERER_ORG_SLUG/msp"
  cp "$orderer_org/orderers/$ORDERER_FQDN/tls/ca.crt" "$stage/$ORDERER_ORG_SLUG/tlsca.pem"
  cp "$orderer_org/orderers/$ORDERER_FQDN/tls/server.crt" "$stage/$ORDERER_ORG_SLUG/orderer-tls-server.crt"
fi

archive="$outbox/$MACHINE-public.tar.gz"
tar -C "$stage" -czf "$archive" .
echo "Wrote $archive (public certificates only)."
