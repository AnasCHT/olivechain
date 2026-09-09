#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

MACHINE_ARG="${1:?usage: repair-orgadmin-role.sh machine1|machine2|machine3|machine4}"

load_versions
load_machine "$MACHINE_ARG"
require_command fabric-ca-client

peer_ca_home="$RUNTIME_DIR/ca-client/$PEER_ORG_SLUG"
peer_ca_tls="$RUNTIME_DIR/ca/$PEER_ORG_SLUG/tls-cert.pem"

peer_org="$CRYPTO_DIR/peerOrganizations/$PEER_ORG_DOMAIN"
peer_admin="$peer_org/users/Admin@$PEER_ORG_DOMAIN"

export FABRIC_CA_CLIENT_HOME="$peer_ca_home"

if [[ ! -s "$peer_ca_home/msp/signcerts/cert.pem" ]]; then
  fabric-ca-client enroll \
    -u "https://admin:${CA_ADMIN_PASSWORD}@localhost:7054" \
    --caname "ca-$PEER_ORG_SLUG" \
    --tls.certfiles "$peer_ca_tls"
fi

fabric-ca-client identity modify orgadmin \
  --caname "ca-$PEER_ORG_SLUG" \
  --type admin \
  --attrs "olivechain.role=orgadmin:ecert" \
  --tls.certfiles "$peer_ca_tls"

rm -rf "$peer_admin/msp"

fabric-ca-client enroll \
  -u "https://orgadmin:${PEER_ADMIN_ENROLL_SECRET}@localhost:7054" \
  --caname "ca-$PEER_ORG_SLUG" \
  -M "$peer_admin/msp" \
  --tls.certfiles "$peer_ca_tls"

rm -rf \
  "$peer_admin/msp/cacerts" \
  "$peer_admin/msp/tlscacerts"

mkdir -p \
  "$peer_admin/msp/cacerts" \
  "$peer_admin/msp/tlscacerts"

cp \
  "$peer_org/msp/cacerts/ca-cert.pem" \
  "$peer_admin/msp/cacerts/ca-cert.pem"

cp \
  "$peer_org/msp/tlscacerts/tlsca-cert.pem" \
  "$peer_admin/msp/tlscacerts/tlsca-cert.pem"

cp \
  "$peer_org/msp/config.yaml" \
  "$peer_admin/msp/config.yaml"

chmod -R go-rwx "$peer_admin"

echo "Re-enrolled $PEER_MSP_ID orgadmin with olivechain.role=orgadmin"
