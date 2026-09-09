#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_versions
load_machine "${1:?usage: enroll-machine.sh machine1}"
assert_no_example_secrets
require_command fabric-ca-client

peer_ca_home="$RUNTIME_DIR/ca-client/$PEER_ORG_SLUG"
peer_ca_tls="$RUNTIME_DIR/ca/$PEER_ORG_SLUG/tls-cert.pem"
peer_org="$CRYPTO_DIR/peerOrganizations/$PEER_ORG_DOMAIN"
peer_node="$peer_org/peers/$PEER_FQDN"
peer_admin="$peer_org/users/Admin@$PEER_ORG_DOMAIN"
peer_app="$peer_org/users/app@$PEER_ORG_DOMAIN"

wait_for_file "$peer_ca_tls"
rm -rf "$peer_ca_home" "$peer_org"
mkdir -p "$peer_ca_home" "$peer_org"
export FABRIC_CA_CLIENT_HOME="$peer_ca_home"

fabric-ca-client enroll -u "https://admin:${CA_ADMIN_PASSWORD}@localhost:7054" \
  --caname "ca-$PEER_ORG_SLUG" --tls.certfiles "$peer_ca_tls"

ca_register --caname "ca-$PEER_ORG_SLUG" --id.name peer0 \
  --id.secret "$PEER_NODE_ENROLL_SECRET" --id.type peer \
  --id.attrs "olivechain.role=$OLIVECHAIN_ROLE:ecert" --tls.certfiles "$peer_ca_tls"
ca_register --caname "ca-$PEER_ORG_SLUG" --id.name orgadmin \
  --id.secret "$PEER_ADMIN_ENROLL_SECRET" --id.type admin \
  --id.attrs "olivechain.role=$OLIVECHAIN_ROLE:ecert" --tls.certfiles "$peer_ca_tls"
ca_register --caname "ca-$PEER_ORG_SLUG" --id.name app \
  --id.secret "$PEER_APP_ENROLL_SECRET" --id.type client \
  --id.attrs "olivechain.role=$OLIVECHAIN_ROLE:ecert" --tls.certfiles "$peer_ca_tls"

fabric-ca-client enroll -u "https://peer0:${PEER_NODE_ENROLL_SECRET}@localhost:7054" \
  --caname "ca-$PEER_ORG_SLUG" -M "$peer_node/msp" --tls.certfiles "$peer_ca_tls"
fabric-ca-client enroll -u "https://peer0:${PEER_NODE_ENROLL_SECRET}@localhost:7054" \
  --caname "ca-$PEER_ORG_SLUG" -M "$peer_node/tls" --enrollment.profile tls \
  --csr.hosts "$PEER_FQDN" --csr.hosts "$MACHINE_FQDN" \
  --csr.hosts localhost --csr.hosts "$MACHINE_IP" --tls.certfiles "$peer_ca_tls"
normalize_tls_msp "$peer_node/tls" server

fabric-ca-client enroll -u "https://orgadmin:${PEER_ADMIN_ENROLL_SECRET}@localhost:7054" \
  --caname "ca-$PEER_ORG_SLUG" -M "$peer_admin/msp" --tls.certfiles "$peer_ca_tls"
fabric-ca-client enroll -u "https://app:${PEER_APP_ENROLL_SECRET}@localhost:7054" \
  --caname "ca-$PEER_ORG_SLUG" -M "$peer_app/msp" --tls.certfiles "$peer_ca_tls"

create_org_msp "$peer_node/msp" "$peer_node/tls" "$peer_org/msp"
copy_node_ou_config "$peer_org/msp" "$peer_node/msp"
copy_node_ou_config "$peer_org/msp" "$peer_admin/msp"
copy_node_ou_config "$peer_org/msp" "$peer_app/msp"

if [[ "$HAS_ORDERER" == "true" ]]; then
  orderer_ca_home="$RUNTIME_DIR/ca-client/$ORDERER_ORG_SLUG"
  orderer_ca_tls="$RUNTIME_DIR/ca/$ORDERER_ORG_SLUG/tls-cert.pem"
  orderer_org="$CRYPTO_DIR/ordererOrganizations/$ORDERER_ORG_DOMAIN"
  orderer_node="$orderer_org/orderers/$ORDERER_FQDN"
  orderer_admin="$orderer_org/users/Admin@$ORDERER_ORG_DOMAIN"
  osnadmin="$orderer_org/users/osnadmin@$ORDERER_ORG_DOMAIN"

  wait_for_file "$orderer_ca_tls"
  rm -rf "$orderer_ca_home" "$orderer_org"
  mkdir -p "$orderer_ca_home" "$orderer_org"
  export FABRIC_CA_CLIENT_HOME="$orderer_ca_home"

  fabric-ca-client enroll -u "https://admin:${ORDERER_CA_ADMIN_PASSWORD}@localhost:8054" \
    --caname "ca-$ORDERER_ORG_SLUG" --tls.certfiles "$orderer_ca_tls"

  ca_register --caname "ca-$ORDERER_ORG_SLUG" --id.name "$ORDERER_NAME" \
    --id.secret "$ORDERER_NODE_ENROLL_SECRET" --id.type orderer --tls.certfiles "$orderer_ca_tls"
  ca_register --caname "ca-$ORDERER_ORG_SLUG" --id.name orgadmin \
    --id.secret "$ORDERER_ADMIN_ENROLL_SECRET" --id.type admin --tls.certfiles "$orderer_ca_tls"
  ca_register --caname "ca-$ORDERER_ORG_SLUG" --id.name osnadmin \
    --id.secret "$OSNADMIN_ENROLL_SECRET" --id.type client --tls.certfiles "$orderer_ca_tls"

  fabric-ca-client enroll -u "https://${ORDERER_NAME}:${ORDERER_NODE_ENROLL_SECRET}@localhost:8054" \
    --caname "ca-$ORDERER_ORG_SLUG" -M "$orderer_node/msp" --tls.certfiles "$orderer_ca_tls"
  fabric-ca-client enroll -u "https://${ORDERER_NAME}:${ORDERER_NODE_ENROLL_SECRET}@localhost:8054" \
    --caname "ca-$ORDERER_ORG_SLUG" -M "$orderer_node/tls" --enrollment.profile tls \
    --csr.hosts "$ORDERER_FQDN" --csr.hosts "$MACHINE_FQDN" \
    --csr.hosts localhost --csr.hosts "$MACHINE_IP" --tls.certfiles "$orderer_ca_tls"
  normalize_tls_msp "$orderer_node/tls" server

  fabric-ca-client enroll -u "https://orgadmin:${ORDERER_ADMIN_ENROLL_SECRET}@localhost:8054" \
    --caname "ca-$ORDERER_ORG_SLUG" -M "$orderer_admin/msp" --tls.certfiles "$orderer_ca_tls"
  fabric-ca-client enroll -u "https://osnadmin:${OSNADMIN_ENROLL_SECRET}@localhost:8054" \
    --caname "ca-$ORDERER_ORG_SLUG" -M "$osnadmin/tls" --enrollment.profile tls \
    --csr.hosts localhost --csr.hosts "$MACHINE_FQDN" --csr.hosts "$MACHINE_IP" \
    --tls.certfiles "$orderer_ca_tls"
  normalize_tls_msp "$osnadmin/tls" client

  create_org_msp "$orderer_node/msp" "$orderer_node/tls" "$orderer_org/msp"
  copy_node_ou_config "$orderer_org/msp" "$orderer_node/msp"
  copy_node_ou_config "$orderer_org/msp" "$orderer_admin/msp"
fi

chmod -R go-rwx "$CRYPTO_DIR"
echo "Created local identities for $MACHINE. Private keys remain under $CRYPTO_DIR."
