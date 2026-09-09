#!/usr/bin/env python3
"""Bootstrap the first wallet-bound orgadmin for an OliveChain organization.

The wallet must already exist on Fabric (create it in the portal first). This
script temporarily creates an unbound Fabric orgadmin identity on the target
organization, binds the selected wallet to a new wallet-aware orgadmin cert,
commits the wallet role grant, then disables the temporary bootstrap identity.
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from olivechain.fabric_client import FabricAgentError, FabricAgentRouter

ORG_MSP = {
    "farmer-org": "FarmerOrgMSP",
    "maker-org": "MakerOrgMSP",
    "courier-org": "CourierOrgMSP",
    "recycler-org": "RecyclerOrgMSP",
}


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def username_for(address: str, prefix: str) -> str:
    suffix = address.split("-", 1)[1].lower()
    return f"{prefix}-{suffix[:12]}-{secrets.token_hex(3)}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("org_id", choices=sorted(ORG_MSP))
    parser.add_argument("wallet_address")
    parser.add_argument("--env", default=str(ROOT / "fabric-app.env"))
    args = parser.parse_args()

    load_env(Path(args.env))
    address = args.wallet_address.strip().upper()
    if not address.startswith("OLIVE-") or len(address) != 30:
        raise SystemExit("invalid OliveChain wallet address")

    router = FabricAgentRouter.from_env()
    try:
        wallet = router.evaluate("GetWallet", [address])
    except Exception as exc:
        raise SystemExit(f"cannot read wallet from Fabric: {exc}") from exc
    if not wallet:
        raise SystemExit("wallet does not exist on Fabric; create/connect it in the portal first")
    if wallet.get("role_status") == "active":
        raise SystemExit(f"wallet already has active role {wallet.get('role')}")

    bootstrap_name = username_for(address, "bootstrap")
    admin_name = username_for(address, "admin")
    bootstrap = None
    admin = None
    try:
        print(f"Creating temporary bootstrap identity on {args.org_id}...")
        bootstrap = router.create_identity(
            args.org_id, bootstrap_name, "Wallet Bootstrap Administrator", "orgadmin"
        )
        print(f"Creating wallet-bound orgadmin identity for {address}...")
        admin = router.create_identity(
            args.org_id,
            admin_name,
            wallet.get("display_name") or address,
            "orgadmin",
            wallet_address=address,
        )
        if not admin.get("client_id_hash") or not admin.get("identity_alias"):
            raise RuntimeError("Gateway Agent did not return the new orgadmin client identity")

        print("Committing wallet role grant to Fabric...")
        result = router.submit_as(
            args.org_id,
            bootstrap["identity_alias"],
            "GrantWalletRole",
            [address, "orgadmin", admin["client_id_hash"], admin["identity_alias"]],
        )
        print("\nWallet administrator activated:")
        print(f"  wallet:   {address}")
        print(f"  org:      {args.org_id}")
        print(f"  MSP:      {ORG_MSP[args.org_id]}")
        print(f"  identity: {admin['identity_alias']}")
        print("Reconnect the wallet in the portal to open Role Administration.")
        return 0
    except (FabricAgentError, RuntimeError, KeyError) as exc:
        if admin and admin.get("identity_alias"):
            try:
                router.set_identity_status(args.org_id, admin["identity_alias"], False)
            except Exception:
                pass
        raise SystemExit(f"bootstrap failed: {exc}") from exc
    finally:
        if bootstrap and bootstrap.get("identity_alias"):
            try:
                router.set_identity_status(args.org_id, bootstrap["identity_alias"], False)
                print("Temporary bootstrap identity disabled.")
            except Exception as exc:
                print(f"WARNING: could not disable bootstrap identity: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
