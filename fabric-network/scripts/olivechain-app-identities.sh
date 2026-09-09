#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

usage() {
  cat <<'EOF'
Usage:
  olivechain-app-identities.sh enroll machine1|machine2|machine3|machine4
  olivechain-app-identities.sh verify machine1|machine2|machine3|machine4
  olivechain-app-identities.sh list   machine1|machine2|machine3|machine4
EOF
}

ACTION="${1:-}"
MACHINE_ARG="${2:-}"
[[ -n "$ACTION" && -n "$MACHINE_ARG" ]] || { usage; exit 1; }

load_versions
load_machine "$MACHINE_ARG"
source "$FABRIC_NETWORK_DIR/chaincode/chaincode.env"
require_command fabric-ca-client
require_command peer

peer_ca_home="$RUNTIME_DIR/ca-client/$PEER_ORG_SLUG"
peer_ca_tls="$RUNTIME_DIR/ca/$PEER_ORG_SLUG/tls-cert.pem"
peer_org="$CRYPTO_DIR/peerOrganizations/$PEER_ORG_DOMAIN"
peer_node="$peer_org/peers/$PEER_FQDN"

wait_for_file "$peer_ca_tls"
[[ -d "$peer_org/msp" ]] || {
  echo "Organization MSP missing: $peer_org/msp" >&2
  exit 1
}

case "$MACHINE_ARG" in
  machine1)
    identities=("farmer-user:farmer")
    ;;
  machine2)
    identities=("mill-user:mill" "laboratory-user:laboratory" "bottler-user:bottler")
    ;;
  machine3)
    identities=("collector-user:collector" "distributor-user:distributor" "retailer-user:retailer" "consumer-portal:consumer")
    ;;
  machine4)
    identities=("processor-user:processor")
    ;;
  *)
    echo "Unsupported machine: $MACHINE_ARG" >&2
    exit 1
    ;;
esac

normalize_client_msp() {
  local target_msp="$1"

  rm -rf "$target_msp/cacerts" "$target_msp/tlscacerts"
  mkdir -p "$target_msp/cacerts" "$target_msp/tlscacerts"

  cp "$peer_org/msp/cacerts/ca-cert.pem" \
     "$target_msp/cacerts/ca-cert.pem"

  cp "$peer_org/msp/tlscacerts/tlsca-cert.pem" \
     "$target_msp/tlscacerts/tlsca-cert.pem"

  cp "$peer_org/msp/config.yaml" \
     "$target_msp/config.yaml"
}

enroll_identities() {
  export FABRIC_CA_CLIENT_HOME="$peer_ca_home"

  if [[ ! -s "$peer_ca_home/msp/signcerts/cert.pem" ]]; then
    fabric-ca-client enroll \
      -u "https://admin:${CA_ADMIN_PASSWORD}@localhost:7054" \
      --caname "ca-$PEER_ORG_SLUG" \
      --tls.certfiles "$peer_ca_tls"
  fi

  for item in "${identities[@]}"; do
    identity="${item%%:*}"
    role="${item##*:}"
    secret="${PEER_APP_ENROLL_SECRET}-${identity}"
    target="$peer_org/users/${identity}@${PEER_ORG_DOMAIN}"

    echo "Registering $identity with role $role..."

    ca_register \
      --caname "ca-$PEER_ORG_SLUG" \
      --id.name "$identity" \
      --id.secret "$secret" \
      --id.type client \
      --id.attrs "olivechain.role=$role:ecert" \
      --tls.certfiles "$peer_ca_tls"

    rm -rf "$target/msp"

    fabric-ca-client enroll \
      -u "https://${identity}:${secret}@localhost:7054" \
      --caname "ca-$PEER_ORG_SLUG" \
      -M "$target/msp" \
      --tls.certfiles "$peer_ca_tls"

    normalize_client_msp "$target/msp"
    chmod -R go-rwx "$target"

    echo "Created $target/msp"
  done
}

verify_identities() {
  export CORE_PEER_LOCALMSPID="$PEER_MSP_ID"
  export CORE_PEER_ADDRESS="localhost:7051"
  export CORE_PEER_TLS_ENABLED=true
  export CORE_PEER_TLS_ROOTCERT_FILE="$peer_node/tls/ca.crt"

  for item in "${identities[@]}"; do
    identity="${item%%:*}"
    expected_role="${item##*:}"
    msp="$peer_org/users/${identity}@${PEER_ORG_DOMAIN}/msp"

    [[ -d "$msp" ]] || {
      echo "Missing identity MSP: $msp" >&2
      exit 1
    }

    echo
    echo "Checking $identity (expected role: $expected_role)"

    output="$(
      CORE_PEER_MSPCONFIGPATH="$msp" \
      peer chaincode query \
        --channelID "$CHANNEL_NAME" \
        --name "$CC_NAME" \
        --ctor '{"Args":["WhoAmI"]}'
    )"

    echo "$output"

    ROLE_JSON="$output" EXPECTED_ROLE="$expected_role" EXPECTED_MSP="$PEER_MSP_ID" \
    python3 - <<'PY'
import json
import os
import sys

raw = os.environ["ROLE_JSON"]
expected_role = os.environ["EXPECTED_ROLE"]
expected_msp = os.environ["EXPECTED_MSP"]

try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("Could not parse WhoAmI response as JSON", file=sys.stderr)
    sys.exit(1)

actual_role = data.get("role")
actual_msp = data.get("msp_id")

if actual_role != expected_role:
    print(f"Role mismatch: expected {expected_role}, got {actual_role}", file=sys.stderr)
    sys.exit(1)

if actual_msp != expected_msp:
    print(f"MSP mismatch: expected {expected_msp}, got {actual_msp}", file=sys.stderr)
    sys.exit(1)

print(f"✓ {actual_msp} / {actual_role}")
PY
  done
}

list_identities() {
  for item in "${identities[@]}"; do
    identity="${item%%:*}"
    role="${item##*:}"
    msp="$peer_org/users/${identity}@${PEER_ORG_DOMAIN}/msp"
    if [[ -d "$msp" ]]; then
      echo "✓ $identity -> $role ($msp)"
    else
      echo "✗ $identity -> $role (not enrolled)"
    fi
  done
}

case "$ACTION" in
  enroll) enroll_identities ;;
  verify) verify_identities ;;
  list) list_identities ;;
  *) usage; exit 1 ;;
esac
