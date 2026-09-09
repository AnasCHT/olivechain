#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

ACTION="${1:?usage: cc-lifecycle.sh <package|install|approve|queryapproved|readiness|commit|verify|query-info> machine1|machine2|machine3|machine4}"
MACHINE_ARG="${2:?machine name required}"

load_versions
load_machine "$MACHINE_ARG"
# shellcheck source=/dev/null
source "$FABRIC_NETWORK_DIR/chaincode/chaincode.env"

CC_SOURCE_PATH="$FABRIC_NETWORK_DIR/chaincode/$CC_SOURCE_DIR"
CC_PACKAGE_DIR="$FABRIC_NETWORK_DIR/chaincode/packages"
CC_PACKAGE_PATH="$CC_PACKAGE_DIR/$CC_PACKAGE_FILE"
CC_PACKAGE_ID_FILE="$CC_PACKAGE_PATH.id"
CC_PACKAGE_SHA_FILE="$CC_PACKAGE_PATH.sha256"

peer_org="$CRYPTO_DIR/peerOrganizations/$PEER_ORG_DOMAIN"
export CORE_PEER_LOCALMSPID="$PEER_MSP_ID"
export CORE_PEER_MSPCONFIGPATH="$peer_org/users/Admin@$PEER_ORG_DOMAIN/msp"
export CORE_PEER_ADDRESS=localhost:7051
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_TLS_ROOTCERT_FILE="$peer_org/peers/$PEER_FQDN/tls/ca.crt"

require_command peer

package_id() {
  [[ -s "$CC_PACKAGE_ID_FILE" ]] || {
    echo "Missing $CC_PACKAGE_ID_FILE" >&2
    exit 1
  }
  tr -d '\r\n' < "$CC_PACKAGE_ID_FILE"
}

file_sha256() {
  local file="$1"
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file" | awk '{print $1}'
  else
    sha256sum "$file" | awk '{print $1}'
  fi
}

validate_package() {
  [[ -s "$CC_PACKAGE_PATH" ]] || { echo "Missing package: $CC_PACKAGE_PATH" >&2; exit 1; }
  [[ -s "$CC_PACKAGE_ID_FILE" ]] || { echo "Missing package ID file: $CC_PACKAGE_ID_FILE" >&2; exit 1; }
  [[ -s "$CC_PACKAGE_SHA_FILE" ]] || { echo "Missing checksum file: $CC_PACKAGE_SHA_FILE" >&2; exit 1; }

  local expected_sha actual_sha expected_id actual_id
  expected_sha="$(tr -d '\r\n' < "$CC_PACKAGE_SHA_FILE")"
  actual_sha="$(file_sha256 "$CC_PACKAGE_PATH")"
  [[ "$expected_sha" == "$actual_sha" ]] || {
    echo "Package SHA-256 mismatch" >&2
    echo "Expected: $expected_sha" >&2
    echo "Actual:   $actual_sha" >&2
    exit 1
  }

  expected_id="$(package_id)"
  actual_id="$(peer lifecycle chaincode calculatepackageid "$CC_PACKAGE_PATH" | tr -d '\r\n')"
  [[ "$expected_id" == "$actual_id" ]] || {
    echo "Package ID mismatch" >&2
    echo "Expected: $expected_id" >&2
    echo "Actual:   $actual_id" >&2
    exit 1
  }

  echo "Package verified: $actual_id"
}

set_orderer_target() {
  if [[ "$HAS_ORDERER" == "true" ]]; then
    ORDERER_ADDRESS="localhost:7050"
    ORDERER_HOST_OVERRIDE="$ORDERER_FQDN"
    ORDERER_CA="$FABRIC_NETWORK_DIR/public-artifacts/current/$ORDERER_ORG_SLUG/tlsca.pem"
  else
    ORDERER_HOST_OVERRIDE="$(sed -n 's/^ORDERER_FQDN=//p' "$FABRIC_NETWORK_DIR/machines/machine1/node.env")"
    ORDERER_ADDRESS="$ORDERER_HOST_OVERRIDE:7050"
    ORDERER_CA="$FABRIC_NETWORK_DIR/public-artifacts/current/ordererorg1/tlsca.pem"
  fi
  [[ -s "$ORDERER_CA" ]] || { echo "Missing orderer TLS CA: $ORDERER_CA" >&2; exit 1; }
}

case "$ACTION" in
  package)
    [[ "$MACHINE" == "machine1" ]] || { echo "Package once on machine1 only" >&2; exit 1; }
    [[ -f "$CC_SOURCE_PATH/go.mod" ]] || { echo "Missing chaincode source: $CC_SOURCE_PATH" >&2; exit 1; }
    [[ -f "$CC_SOURCE_PATH/go.sum" ]] || { echo "Missing go.sum; prepare dependencies first" >&2; exit 1; }
    [[ -d "$CC_SOURCE_PATH/vendor" ]] || { echo "Missing vendor directory" >&2; exit 1; }
    mkdir -p "$CC_PACKAGE_DIR"
    rm -f "$CC_PACKAGE_PATH" "$CC_PACKAGE_ID_FILE" "$CC_PACKAGE_SHA_FILE"
    peer lifecycle chaincode package "$CC_PACKAGE_PATH" \
      --path "$CC_SOURCE_PATH" \
      --lang "$CC_LANGUAGE" \
      --label "$CC_LABEL"
    peer lifecycle chaincode calculatepackageid "$CC_PACKAGE_PATH" > "$CC_PACKAGE_ID_FILE"
    file_sha256 "$CC_PACKAGE_PATH" > "$CC_PACKAGE_SHA_FILE"
    echo "Package: $CC_PACKAGE_PATH"
    echo "Package ID: $(package_id)"
    echo "SHA-256: $(cat "$CC_PACKAGE_SHA_FILE")"
    ;;

  install)
    validate_package
    pid="$(package_id)"
    if peer lifecycle chaincode queryinstalled 2>/dev/null | grep -Fq "$pid"; then
      echo "Already installed: $pid"
    else
      peer lifecycle chaincode install "$CC_PACKAGE_PATH"
    fi
    peer lifecycle chaincode queryinstalled
    ;;

  approve)
    validate_package
    set_orderer_target
    pid="$(package_id)"
    peer lifecycle chaincode approveformyorg \
      -o "$ORDERER_ADDRESS" \
      --ordererTLSHostnameOverride "$ORDERER_HOST_OVERRIDE" \
      --channelID "$CHANNEL_NAME" \
      --name "$CC_NAME" \
      --version "$CC_VERSION" \
      --package-id "$pid" \
      --sequence "$CC_SEQUENCE" \
      --signature-policy "$CC_ENDORSEMENT_POLICY" \
      --tls \
      --cafile "$ORDERER_CA" \
      --waitForEvent
    peer lifecycle chaincode queryapproved \
      --channelID "$CHANNEL_NAME" \
      --name "$CC_NAME" \
      --sequence "$CC_SEQUENCE"
    ;;

  queryapproved)
    peer lifecycle chaincode queryapproved \
      --channelID "$CHANNEL_NAME" \
      --name "$CC_NAME" \
      --sequence "$CC_SEQUENCE"
    ;;

  readiness)
    peer lifecycle chaincode checkcommitreadiness \
      --channelID "$CHANNEL_NAME" \
      --name "$CC_NAME" \
      --version "$CC_VERSION" \
      --sequence "$CC_SEQUENCE" \
      --signature-policy "$CC_ENDORSEMENT_POLICY" \
      --output json
    ;;

  commit)
    [[ "$MACHINE" == "machine1" ]] || { echo "Commit from machine1" >&2; exit 1; }
    set_orderer_target
    p1="localhost"
    p2="$(sed -n 's/^PEER_FQDN=//p' "$FABRIC_NETWORK_DIR/machines/machine2/node.env")"
    p3="$(sed -n 's/^PEER_FQDN=//p' "$FABRIC_NETWORK_DIR/machines/machine3/node.env")"
    p4="$(sed -n 's/^PEER_FQDN=//p' "$FABRIC_NETWORK_DIR/machines/machine4/node.env")"
    peer lifecycle chaincode commit \
      -o "$ORDERER_ADDRESS" \
      --ordererTLSHostnameOverride "$ORDERER_HOST_OVERRIDE" \
      --channelID "$CHANNEL_NAME" \
      --name "$CC_NAME" \
      --version "$CC_VERSION" \
      --sequence "$CC_SEQUENCE" \
      --signature-policy "$CC_ENDORSEMENT_POLICY" \
      --peerAddresses "localhost:7051" \
      --tlsRootCertFiles "$FABRIC_NETWORK_DIR/public-artifacts/current/farmer/tlsca.pem" \
      --peerAddresses "localhost:8051" \
      --tlsRootCertFiles "$FABRIC_NETWORK_DIR/public-artifacts/current/maker/tlsca.pem" \
      --peerAddresses "localhost:9051" \
      --tlsRootCertFiles "$FABRIC_NETWORK_DIR/public-artifacts/current/courier/tlsca.pem" \
      --peerAddresses "localhost:10051" \
      --tlsRootCertFiles "$FABRIC_NETWORK_DIR/public-artifacts/current/recycler/tlsca.pem" \
      --tls \
      --cafile "$ORDERER_CA" \
      --waitForEvent
    ;;

  verify)
    peer lifecycle chaincode querycommitted \
      --channelID "$CHANNEL_NAME" \
      --name "$CC_NAME"
    ;;

  query-info)
    peer chaincode query \
      --channelID "$CHANNEL_NAME" \
      --name "$CC_NAME" \
      --ctor '{"Args":["GetContractInfo"]}'
    ;;

  *)
    echo "Unknown action: $ACTION" >&2
    exit 1
    ;;
esac
