#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_versions
load_machine "${1:?usage: stop-local.sh machine1}"
require_command docker
compose compose-node.yaml down || true
compose compose-ca.yaml down || true
