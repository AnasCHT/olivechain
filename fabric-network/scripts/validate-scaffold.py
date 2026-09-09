#!/usr/bin/env python3
from pathlib import Path
import sys
import yaml

root = Path(__file__).resolve().parents[1]
errors = []

required = [
    root / "configtx/configtx.yaml",
    root / "topology.yaml",
    root / "versions.env",
]
for machine in range(1, 5):
    base = root / f"machines/machine{machine}"
    required += [base / "node.env", base / ".env.example", base / "compose-ca.yaml", base / "compose-node.yaml"]
for path in required:
    if not path.is_file():
        errors.append(f"missing: {path.relative_to(root)}")

for path in [root / "topology.yaml", root / "configtx/configtx.yaml"] + [
    root / f"machines/machine{i}/compose-ca.yaml" for i in range(1, 5)
] + [root / f"machines/machine{i}/compose-node.yaml" for i in range(1, 5)]:
    try:
        yaml.safe_load(path.read_text())
    except Exception as exc:
        errors.append(f"invalid YAML {path.relative_to(root)}: {exc}")

config = (root / "configtx/configtx.yaml").read_text()
for token in [
    "FarmerOrgMSP", "MakerOrgMSP", "CourierOrgMSP", "RecyclerOrgMSP",
    "OrdererOrg1MSP", "OrdererOrg2MSP", "OrdererOrg3MSP",
    "orderer1.ordererorg1.olivechain.local",
    "orderer2.ordererorg2.olivechain.local",
    "orderer3.ordererorg3.olivechain.local",
]:
    if token not in config:
        errors.append(f"configtx.yaml missing {token}")

for machine in range(1, 5):
    compose = (root / f"machines/machine{machine}/compose-node.yaml").read_text()
    if "CORE_LEDGER_STATE_STATEDATABASE: CouchDB" not in compose:
        errors.append(f"machine{machine} peer does not select CouchDB")
    if '"5984:5984"' in compose or "5984:5984" in compose:
        errors.append(f"machine{machine} publishes CouchDB port")

if errors:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    raise SystemExit(1)
print("Fabric scaffold validation passed.")
