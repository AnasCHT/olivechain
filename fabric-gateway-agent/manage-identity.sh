#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$PROJECT/fabric-network/scripts/lib.sh"

ACTION="${1:-}"
MACHINE_ARG="${2:-}"
[[ -n "$ACTION" && -n "$MACHINE_ARG" ]] || {
  echo "usage: manage-identity.sh create|status|list machineN ..." >&2
  exit 2
}

load_versions
load_machine "$MACHINE_ARG"
require_command fabric-ca-client
require_command python3
require_command openssl

DYNAMIC_FILE="${FABRIC_DYNAMIC_IDENTITY_FILE:-$SCRIPT_DIR/data/${MACHINE_ARG}-identities.json}"
mkdir -p "$(dirname "$DYNAMIC_FILE")"
peer_ca_home="$RUNTIME_DIR/ca-client/$PEER_ORG_SLUG"
peer_ca_tls="$RUNTIME_DIR/ca/$PEER_ORG_SLUG/tls-cert.pem"
peer_org="$CRYPTO_DIR/peerOrganizations/$PEER_ORG_DOMAIN"

allowed_role() {
  local role="$1"
  case "$MACHINE_ARG:$role" in
    machine1:farmer|machine1:orgadmin|\
    machine2:mill|machine2:laboratory|machine2:bottler|machine2:orgadmin|\
    machine3:collector|machine3:distributor|machine3:retailer|machine3:consumer|machine3:orgadmin|\
    machine4:processor|machine4:orgadmin) return 0 ;;
    *) return 1 ;;
  esac
}

validate_username() {
  [[ "$1" =~ ^[a-z0-9][a-z0-9_-]{2,63}$ ]] || {
    echo "username must be 3-64 lowercase letters, digits, hyphens or underscores" >&2
    exit 3
  }
}

case "$ACTION" in
  create)
    username="${3:?username required}"
    role="${4:?role required}"
    display_name="${5:?display name required}"
    wallet_address="${6:-}"
    validate_username "$username"
    allowed_role "$role" || { echo "role $role is not valid on $MACHINE_ARG" >&2; exit 4; }

    alias="user:$username"
    ca_name="portal-$username"
    relative_dir="$ca_name@$PEER_ORG_DOMAIN"
    target="$peer_org/users/$relative_dir"

    if [[ -f "$DYNAMIC_FILE" ]] && python3 - "$DYNAMIC_FILE" "$alias" <<'PY'
import json, sys
from pathlib import Path
path=Path(sys.argv[1]); alias=sys.argv[2]
try: data=json.loads(path.read_text())
except Exception: data={}
raise SystemExit(0 if alias in data.get("identities", {}) else 1)
PY
    then
      echo "identity alias $alias already exists" >&2
      exit 5
    fi

    "$PROJECT/fabric-network/scripts/start-cas.sh" "$MACHINE_ARG" >&2
    wait_for_file "$peer_ca_tls"
    export FABRIC_CA_CLIENT_HOME="$peer_ca_home"
    if [[ ! -s "$peer_ca_home/msp/signcerts/cert.pem" ]]; then
      fabric-ca-client enroll \
        -u "https://admin:${CA_ADMIN_PASSWORD}@localhost:7054" \
        --caname "ca-$PEER_ORG_SLUG" \
        --tls.certfiles "$peer_ca_tls" >&2
    fi

    secret="$(openssl rand -hex 24)"
    attrs="olivechain.role=$role:ecert,olivechain.user_id=$username:ecert"
    if [[ -n "$wallet_address" ]]; then
      [[ "$wallet_address" =~ ^OLIVE-[A-F0-9]{24}$ ]] || { echo "invalid OliveChain wallet address" >&2; exit 7; }
      attrs+=",olivechain.wallet=$wallet_address:ecert"
    fi
    fabric-ca-client register \
      --caname "ca-$PEER_ORG_SLUG" \
      --id.name "$ca_name" \
      --id.secret "$secret" \
      --id.type client \
      --id.attrs "$attrs" \
      --tls.certfiles "$peer_ca_tls" >&2

    rm -rf "$target/msp"
    fabric-ca-client enroll \
      -u "https://${ca_name}:${secret}@localhost:7054" \
      --caname "ca-$PEER_ORG_SLUG" \
      -M "$target/msp" \
      --tls.certfiles "$peer_ca_tls" >&2

    rm -rf "$target/msp/cacerts" "$target/msp/tlscacerts"
    mkdir -p "$target/msp/cacerts" "$target/msp/tlscacerts"
    cp "$peer_org/msp/cacerts/ca-cert.pem" "$target/msp/cacerts/ca-cert.pem"
    cp "$peer_org/msp/tlscacerts/tlsca-cert.pem" "$target/msp/tlscacerts/tlsca-cert.pem"
    cp "$peer_org/msp/config.yaml" "$target/msp/config.yaml"
    chmod -R go-rwx "$target"

    python3 - "$DYNAMIC_FILE" "$alias" "$username" "$display_name" "$role" "$relative_dir" "$PEER_MSP_ID" "$wallet_address" <<'PY'
import json, os, sys, time
from pathlib import Path
path=Path(sys.argv[1]); alias, username, display_name, role, relative_dir, msp_id, wallet_address=sys.argv[2:]
try: data=json.loads(path.read_text())
except Exception: data={"schema_version":1,"identities":{}}
data.setdefault("schema_version",1); identities=data.setdefault("identities",{})
row={"identity_alias":alias,"username":username,"display_name":display_name,
     "role":role,"relative_dir":relative_dir,"msp_id":msp_id,"wallet_address":wallet_address,"active":True,
     "created_at":int(time.time()),"updated_at":int(time.time())}
identities[alias]=row
path.parent.mkdir(parents=True,exist_ok=True)
tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
os.chmod(tmp,0o600); os.replace(tmp,path)
print(json.dumps(row,separators=(",",":")))
PY
    ;;

  status)
    alias="${3:?identity alias required}"
    active="${4:?true or false required}"
    [[ "$active" == "true" || "$active" == "false" ]] || { echo "active must be true or false" >&2; exit 6; }
    python3 - "$DYNAMIC_FILE" "$alias" "$active" <<'PY'
import json, os, sys, time
from pathlib import Path
path=Path(sys.argv[1]); alias=sys.argv[2]; active=sys.argv[3]=="true"
if not path.exists(): raise SystemExit("dynamic identity store does not exist")
data=json.loads(path.read_text()); row=data.get("identities",{}).get(alias)
if row is None: raise SystemExit(f"identity {alias} not found")
row["active"]=active; row["updated_at"]=int(time.time())
tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
os.chmod(tmp,0o600); os.replace(tmp,path)
print(json.dumps(row,separators=(",",":")))
PY
    ;;

  list)
    python3 - "$DYNAMIC_FILE" <<'PY'
import json, sys
from pathlib import Path
path=Path(sys.argv[1])
if not path.exists(): print('{"identities":[]}')
else:
 data=json.loads(path.read_text())
 print(json.dumps({"identities":list(data.get("identities",{}).values())},separators=(",",":")))
PY
    ;;

  *) echo "unknown action: $ACTION" >&2; exit 2 ;;
esac
