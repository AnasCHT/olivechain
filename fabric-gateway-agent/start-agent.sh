#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$PROJECT/fabric-network/scripts/lib.sh"

MACHINE_ARG="${1:?usage: start-agent.sh machine1|machine2|machine3|machine4}"
load_versions
load_machine "$MACHINE_ARG"
source "$PROJECT/fabric-network/chaincode/chaincode.env"

peer_org="$CRYPTO_DIR/peerOrganizations/$PEER_ORG_DOMAIN"
users="$peer_org/users"

case "$MACHINE_ARG" in
  machine1)
    default_port=9080
    identities=$(cat <<JSON
{"farmer":"farmer-user@$PEER_ORG_DOMAIN","orgadmin":"Admin@$PEER_ORG_DOMAIN"}
JSON
)
    ;;
  machine2)
    default_port=9080
    identities=$(cat <<JSON
{"mill":"mill-user@$PEER_ORG_DOMAIN","laboratory":"laboratory-user@$PEER_ORG_DOMAIN","bottler":"bottler-user@$PEER_ORG_DOMAIN","orgadmin":"Admin@$PEER_ORG_DOMAIN"}
JSON
)
    ;;
  machine3)
    default_port=9080
    identities=$(cat <<JSON
{"collector":"collector-user@$PEER_ORG_DOMAIN","distributor":"distributor-user@$PEER_ORG_DOMAIN","retailer":"retailer-user@$PEER_ORG_DOMAIN","consumer":"consumer-portal@$PEER_ORG_DOMAIN","orgadmin":"Admin@$PEER_ORG_DOMAIN"}
JSON
)
    ;;
  machine4)
    default_port=9080
    identities=$(cat <<JSON
{"processor":"processor-user@$PEER_ORG_DOMAIN","orgadmin":"Admin@$PEER_ORG_DOMAIN"}
JSON
)
    ;;
  *) echo "unsupported machine $MACHINE_ARG" >&2; exit 1 ;;
esac

: "${OLIVECHAIN_AGENT_TOKEN:?set OLIVECHAIN_AGENT_TOKEN in the machine .env or shell}"
export OLIVECHAIN_AGENT_TOKEN
export OLIVECHAIN_AGENT_BIND="${OLIVECHAIN_AGENT_BIND:-0.0.0.0}"
export OLIVECHAIN_AGENT_PORT="${OLIVECHAIN_AGENT_PORT:-$default_port}"
export FABRIC_MSP_ID="$PEER_MSP_ID"
export FABRIC_PEER_ENDPOINT="localhost:7051"
export FABRIC_PEER_HOST_ALIAS="$PEER_FQDN"
export FABRIC_TLS_CERT_PATH="$peer_org/peers/$PEER_FQDN/tls/ca.crt"
export FABRIC_IDENTITY_ROOT="$users"
export FABRIC_IDENTITY_MAP="$identities"
export OLIVECHAIN_MACHINE="$MACHINE_ARG"
export FABRIC_DYNAMIC_IDENTITY_FILE="${FABRIC_DYNAMIC_IDENTITY_FILE:-$SCRIPT_DIR/data/${MACHINE_ARG}-identities.json}"
export FABRIC_IDENTITY_ADMIN_SCRIPT="${FABRIC_IDENTITY_ADMIN_SCRIPT:-$SCRIPT_DIR/manage-identity.sh}"
export FABRIC_CHANNEL_NAME="$CHANNEL_NAME"
export FABRIC_CHAINCODE_NAME="$CC_NAME"

cd "$SCRIPT_DIR"
exec npm start
