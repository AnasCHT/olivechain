#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_versions
load_machine "${1:?usage: join-orderer.sh machine1}"
[[ "$HAS_ORDERER" == "true" ]] || { echo "$MACHINE has no orderer" >&2; exit 1; }
require_command osnadmin

block="$FABRIC_NETWORK_DIR/channel-artifacts/$CHANNEL_NAME.block"
osn_tls="$CRYPTO_DIR/ordererOrganizations/$ORDERER_ORG_DOMAIN/users/osnadmin@$ORDERER_ORG_DOMAIN/tls"
[[ -s "$block" ]] || { echo "Missing channel block" >&2; exit 1; }

set +e
output="$(osnadmin channel join \
  --channelID "$CHANNEL_NAME" \
  --config-block "$block" \
  -o localhost:7053 \
  --ca-file "$osn_tls/ca.crt" \
  --client-cert "$osn_tls/client.crt" \
  --client-key "$osn_tls/client.key" 2>&1)"
rc=$?
set -e
if (( rc != 0 )) && ! grep -qiE 'exists|already' <<<"$output"; then
  echo "$output" >&2
  exit "$rc"
fi
echo "$output"
osnadmin channel list -o localhost:7053 \
  --ca-file "$osn_tls/ca.crt" \
  --client-cert "$osn_tls/client.crt" \
  --client-key "$osn_tls/client.key"
