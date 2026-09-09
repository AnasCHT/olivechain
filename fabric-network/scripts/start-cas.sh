#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_versions
load_machine "${1:?usage: start-cas.sh machine1}"
assert_no_example_secrets
require_command docker
mkdir -p "$RUNTIME_DIR/ca"
compose compose-ca.yaml up -d
wait_for_file "$RUNTIME_DIR/ca/$PEER_ORG_SLUG/tls-cert.pem"
if [[ "$HAS_ORDERER" == "true" ]]; then
  wait_for_file "$RUNTIME_DIR/ca/$ORDERER_ORG_SLUG/tls-cert.pem"
fi
compose compose-ca.yaml ps
