"""Create a local OliveChain backup (ledger + registry + evidence).

Runs without the server, so it is safe for cron. Writes a timestamped
gzipped tar containing checksummed copies plus a chain summary.

    python scripts/backup.py [--out DIR]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from olivechain import Ledger, Registry
from olivechain.backup import make_backup
from olivechain.ledger import GENESIS_HASH

ap = argparse.ArgumentParser(description="Create an OliveChain backup archive.")
ap.add_argument("--out", default="backups", help="output directory (default: backups/)")
args = ap.parse_args()

registry_path = "data/registry.json"
ledger_path = "data/ledger.jsonl"
evidence_root = "evidence_store"

summary = {}
if os.path.exists(ledger_path):
    ledger = Ledger(Registry(registry_path), ledger_path)
    ok, _ = ledger.verify_chain()
    evs = ledger.all()
    summary = {"height": len(evs),
               "head_hash": evs[-1].event_hash if evs else GENESIS_HASH,
               "chain_valid": ok}
    if not ok:
        print("WARNING: chain does not verify — backing up anyway.", file=sys.stderr)

data = make_backup(registry_path, ledger_path, evidence_root, extra=summary)

os.makedirs(args.out, exist_ok=True)
name = f"olivechain-backup-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}.tar.gz"
path = os.path.join(args.out, name)
with open(path, "wb") as f:
    f.write(data)

print(f"Wrote {path} ({len(data):,} bytes)"
      + (f", height {summary['height']}, chain_valid={summary['chain_valid']}" if summary else ""))
