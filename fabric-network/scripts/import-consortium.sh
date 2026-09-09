#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_versions
archive="${1:?usage: import-consortium.sh /path/to/olivechain-consortium.tar.gz}"
[[ -s "$archive" ]] || { echo "Archive not found: $archive" >&2; exit 1; }
tar -xzf "$archive" -C "$FABRIC_NETWORK_DIR"
[[ -s "$FABRIC_NETWORK_DIR/channel-artifacts/$CHANNEL_NAME.block" ]] || {
  echo "Imported archive does not contain the channel block" >&2; exit 1;
}
echo "Imported consortium public material and channel block."
