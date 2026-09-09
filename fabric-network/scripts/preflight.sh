#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_versions
load_machine "${1:?usage: preflight.sh machine1}"
assert_no_example_secrets
require_command docker
require_command getent

docker info >/dev/null
for host in \
  peer0.farmer.olivechain.local orderer1.ordererorg1.olivechain.local \
  peer0.maker.olivechain.local orderer2.ordererorg2.olivechain.local \
  peer0.courier.olivechain.local orderer3.ordererorg3.olivechain.local \
  peer0.recycler.olivechain.local; do
  getent hosts "$host" >/dev/null || { echo "Cannot resolve $host" >&2; exit 1; }
done

echo "$MACHINE preflight passed."
