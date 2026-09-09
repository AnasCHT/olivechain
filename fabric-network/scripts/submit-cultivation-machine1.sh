#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT:-$HOME/olivechain-main}"
SCRIPT_DIR="$PROJECT/fabric-network/scripts"

# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_versions
load_machine machine1
source "$FABRIC_NETWORK_DIR/chaincode/chaincode.env"

usage() {
  cat <<'EOF'
Usage:
  submit-cultivation-machine1.sh \
    BATCH_ID FARM_ID PLOT_ID CULTIVAR PRACTICES_JSON [EVENT_ID]

Example:
  submit-cultivation-machine1.sh \
    BATCH-2026-001 FARM-001 PLOT-A \
    "Picholine Marocaine" \
    '{"irrigation":"drip","treatments":[],"certification":"organic"}'
EOF
}

[[ $# -ge 5 && $# -le 6 ]] || { usage; exit 1; }

BATCH_ID="$1"
FARM_ID="$2"
PLOT_ID="$3"
CULTIVAR="$4"
PRACTICES_JSON="$5"
EVENT_ID="${6:-cultivation-${BATCH_ID}-$(date -u +%Y%m%dT%H%M%SZ)}"

peer_org="$CRYPTO_DIR/peerOrganizations/$PEER_ORG_DOMAIN"
farmer_msp="$peer_org/users/farmer-user@$PEER_ORG_DOMAIN/msp"

[[ -d "$farmer_msp" ]] || {
  echo "Farmer identity not found: $farmer_msp" >&2
  echo "Run olivechain-app-identities.sh enroll machine1 first." >&2
  exit 1
}

export CORE_PEER_LOCALMSPID="$PEER_MSP_ID"
export CORE_PEER_MSPCONFIGPATH="$farmer_msp"
export CORE_PEER_ADDRESS="localhost:7051"
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_TLS_ROOTCERT_FILE="$peer_org/peers/$PEER_FQDN/tls/ca.crt"

echo "Caller identity:"
peer chaincode query \
  --channelID "$CHANNEL_NAME" \
  --name "$CC_NAME" \
  --ctor '{"Args":["WhoAmI"]}'

PAYLOAD="$(
  FARM_ID="$FARM_ID" \
  PLOT_ID="$PLOT_ID" \
  CULTIVAR="$CULTIVAR" \
  PRACTICES_JSON="$PRACTICES_JSON" \
  python3 - <<'PY'
import json
import os

practices = json.loads(os.environ["PRACTICES_JSON"])
payload = {
    "farm_id": os.environ["FARM_ID"],
    "plot_id": os.environ["PLOT_ID"],
    "cultivar": os.environ["CULTIVAR"],
    "practices": practices,
}
print(json.dumps(payload, separators=(",", ":")))
PY
)"

CTOR="$(
  EVENT_ID="$EVENT_ID" \
  BATCH_ID="$BATCH_ID" \
  PAYLOAD="$PAYLOAD" \
  python3 - <<'PY'
import json
import os

args = [
    "SubmitEvent",
    os.environ["EVENT_ID"],
    "cultivation",
    os.environ["BATCH_ID"],
    os.environ["PAYLOAD"],
    "[]",
]
print(json.dumps({"Args": args}, separators=(",", ":")))
PY
)"

echo
echo "Submitting cultivation event:"
echo "  Event: $EVENT_ID"
echo "  Batch: $BATCH_ID"
echo "  Farm:  $FARM_ID"
echo "  Plot:  $PLOT_ID"

peer chaincode invoke \
  --connTimeout 15s \
  --orderer "localhost:7050" \
  --ordererTLSHostnameOverride "$ORDERER_FQDN" \
  --tls \
  --cafile "$FABRIC_NETWORK_DIR/public-artifacts/current/ordererorg1/tlsca.pem" \
  --channelID "$CHANNEL_NAME" \
  --name "$CC_NAME" \
  --peerAddresses "localhost:7051" \
  --tlsRootCertFiles "$FABRIC_NETWORK_DIR/public-artifacts/current/farmer/tlsca.pem" \
  --peerAddresses "$M2_IP:7051" \
  --tlsRootCertFiles "$FABRIC_NETWORK_DIR/public-artifacts/current/maker/tlsca.pem" \
  --ctor "$CTOR" \
  --waitForEvent \
  --waitForEventTimeout 60s

echo
echo "Committed. Querying batch history:"

QUERY_CTOR="$(
  BATCH_ID="$BATCH_ID" \
  python3 - <<'PY'
import json
import os
print(json.dumps({
    "Args": ["GetEventsForSubject", os.environ["BATCH_ID"], "false"]
}, separators=(",", ":")))
PY
)"

peer chaincode query \
  --channelID "$CHANNEL_NAME" \
  --name "$CC_NAME" \
  --ctor "$QUERY_CTOR"
