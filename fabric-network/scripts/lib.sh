#!/usr/bin/env bash
set -euo pipefail

FABRIC_NETWORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$FABRIC_NETWORK_DIR/.." && pwd)"

load_versions() {
  set -a
  # shellcheck source=/dev/null
  source "$FABRIC_NETWORK_DIR/versions.env"
  set +a
  export PATH="$FABRIC_NETWORK_DIR/bin:$PATH"
}
load_machine() {
  local machine="${1:?machine name required, e.g. machine1}"
  local dir="$FABRIC_NETWORK_DIR/machines/$machine"
  [[ -d "$dir" ]] || { echo "Unknown machine: $machine" >&2; exit 1; }
  [[ -f "$dir/.env" ]] || { echo "Missing $dir/.env; copy .env.example first" >&2; exit 1; }
  set -a
  # shellcheck source=/dev/null
  source "$dir/node.env"
  # shellcheck source=/dev/null
  source "$dir/.env"
  set +a
  MACHINE_DIR="$dir"
  RUNTIME_DIR="$FABRIC_NETWORK_DIR/runtime/$machine"
  CRYPTO_DIR="$RUNTIME_DIR/crypto"
  export MACHINE_DIR RUNTIME_DIR CRYPTO_DIR
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    echo "Run fabric-network/scripts/install-tools.sh first." >&2
    exit 1
  }
}

compose() {
  local file="${1:?compose file required}"
  shift
  docker compose --env-file "$FABRIC_NETWORK_DIR/versions.env" --env-file "$MACHINE_DIR/.env" -f "$MACHINE_DIR/$file" "$@"
}

wait_for_file() {
  local file="$1" timeout="${2:-90}" elapsed=0
  until [[ -s "$file" ]]; do
    if (( elapsed >= timeout )); then
      echo "Timed out waiting for $file" >&2
      exit 1
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
}

assert_no_example_secrets() {
  if grep -q 'replace-' "$MACHINE_DIR/.env"; then
    echo "Refusing to continue: replace every example secret in $MACHINE_DIR/.env" >&2
    exit 1
  fi
}

normalize_tls_msp() {
  local dir="$1" prefix="${2:-server}"
  local key cert ca
  key="$(find "$dir/keystore" -type f | head -n 1)"
  cert="$(find "$dir/signcerts" -type f | head -n 1)"
  ca="$(find "$dir/tlscacerts" -type f | head -n 1)"
  [[ -n "$key" && -n "$cert" && -n "$ca" ]] || { echo "Incomplete TLS MSP at $dir" >&2; exit 1; }
  cp "$key" "$dir/${prefix}.key"
  cp "$cert" "$dir/${prefix}.crt"
  cp "$ca" "$dir/ca.crt"
}

create_org_msp() {
  local source_enrollment_msp="$1" source_tls_msp="$2" target_msp="$3"
  rm -rf "$target_msp"
  mkdir -p "$target_msp/cacerts" "$target_msp/tlscacerts"
  cp "$(find "$source_enrollment_msp/cacerts" -type f | head -n1)" "$target_msp/cacerts/ca-cert.pem"
  cp "$(find "$source_tls_msp/tlscacerts" -type f | head -n1)" "$target_msp/tlscacerts/tlsca-cert.pem"
  cat > "$target_msp/config.yaml" <<'EOF'
NodeOUs:
  Enable: true
  ClientOUIdentifier:
    Certificate: cacerts/ca-cert.pem
    OrganizationalUnitIdentifier: client
  PeerOUIdentifier:
    Certificate: cacerts/ca-cert.pem
    OrganizationalUnitIdentifier: peer
  AdminOUIdentifier:
    Certificate: cacerts/ca-cert.pem
    OrganizationalUnitIdentifier: admin
  OrdererOUIdentifier:
    Certificate: cacerts/ca-cert.pem
    OrganizationalUnitIdentifier: orderer
EOF
}

copy_node_ou_config() {
  local org_msp="$1" node_msp="$2"
  cp "$org_msp/config.yaml" "$node_msp/config.yaml"
}
ca_register() {
  local output rc
  set +e
  output="$(fabric-ca-client register "$@" 2>&1)"
  rc=$?
  set -e
  if (( rc != 0 )) && ! grep -qi "already registered" <<<"$output"; then
    echo "$output" >&2
    return "$rc"
  fi
  echo "$output"
}
