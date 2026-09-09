#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_versions

mkdir -p "$FABRIC_NETWORK_DIR/bin" "$FABRIC_NETWORK_DIR/.downloads"

os="$(uname -s | tr '[:upper:]' '[:lower:]')"
arch_raw="$(uname -m)"
case "$arch_raw" in
  x86_64|amd64) arch=amd64 ;;
  aarch64|arm64) arch=arm64 ;;
  *) echo "Unsupported architecture: $arch_raw" >&2; exit 1 ;;
esac
[[ "$os" == "linux" ]] || { echo "The four Fabric hosts must run Linux; detected $os" >&2; exit 1; }

fabric_tgz="$FABRIC_NETWORK_DIR/.downloads/hyperledger-fabric-${os}-${arch}-${FABRIC_VERSION}.tar.gz"
ca_tgz="$FABRIC_NETWORK_DIR/.downloads/hyperledger-fabric-ca-${os}-${arch}-${FABRIC_CA_VERSION}.tar.gz"

if [[ ! -s "$fabric_tgz" ]]; then
  curl -fL "https://github.com/hyperledger/fabric/releases/download/v${FABRIC_VERSION}/hyperledger-fabric-${os}-${arch}-${FABRIC_VERSION}.tar.gz" -o "$fabric_tgz"
fi
if [[ ! -s "$ca_tgz" ]]; then
  curl -fL "https://github.com/hyperledger/fabric-ca/releases/download/v${FABRIC_CA_VERSION}/hyperledger-fabric-ca-${os}-${arch}-${FABRIC_CA_VERSION}.tar.gz" -o "$ca_tgz"
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/fabric" "$tmp/ca"
tar -xzf "$fabric_tgz" -C "$tmp/fabric"
tar -xzf "$ca_tgz" -C "$tmp/ca"
cp "$tmp/fabric/bin/"* "$FABRIC_NETWORK_DIR/bin/"
cp "$tmp/ca/bin/"* "$FABRIC_NETWORK_DIR/bin/"
chmod +x "$FABRIC_NETWORK_DIR/bin/"*

docker pull "hyperledger/fabric-peer:${FABRIC_VERSION}"
docker pull "hyperledger/fabric-orderer:${FABRIC_VERSION}"
docker pull "hyperledger/fabric-ca:${FABRIC_CA_VERSION}"
docker pull "couchdb:${COUCHDB_VERSION}"

echo "Installed Fabric ${FABRIC_VERSION}, Fabric CA ${FABRIC_CA_VERSION}, CouchDB ${COUCHDB_VERSION}."
