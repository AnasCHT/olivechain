#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_versions
load_machine "${1:?usage: repair-local-msps.sh machine1}"

repair_msp_tree() {
    local org_root="$1"
    local org_msp="$org_root/msp"

    for required in \
        "$org_msp/config.yaml" \
        "$org_msp/cacerts/ca-cert.pem" \
        "$org_msp/tlscacerts/tlsca-cert.pem"
    do
        [[ -s "$required" ]] || {
            echo "Required organization MSP file missing: $required" >&2
            exit 1
        }
    done

    while IFS= read -r target_msp; do
        # Skip the organization MSP itself.
        [[ "$target_msp" == "$org_msp" ]] && continue

        # Only repair local node or user MSPs.
        if [[ -d "$target_msp/signcerts" ||
              -d "$target_msp/keystore" ]]; then

            mkdir -p \
                "$target_msp/cacerts" \
                "$target_msp/tlscacerts"

            cp -f \
                "$org_msp/cacerts/ca-cert.pem" \
                "$target_msp/cacerts/ca-cert.pem"

            cp -f \
                "$org_msp/tlscacerts/tlsca-cert.pem" \
                "$target_msp/tlscacerts/tlsca-cert.pem"

            cp -f \
                "$org_msp/config.yaml" \
                "$target_msp/config.yaml"

            echo "Repaired: $target_msp"
        fi
    done < <(find "$org_root" -type d -name msp -print)
}

peer_org="$CRYPTO_DIR/peerOrganizations/$PEER_ORG_DOMAIN"
repair_msp_tree "$peer_org"

if [[ "$HAS_ORDERER" == "true" ]]; then
    orderer_org="$CRYPTO_DIR/ordererOrganizations/$ORDERER_ORG_DOMAIN"
    repair_msp_tree "$orderer_org"
fi

echo "MSP certificate references repaired for $MACHINE."
