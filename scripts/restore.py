"""Restore an OliveChain backup created by scripts/backup.py or /admin/export.

Extracts (checksum-verified, path-traversal-safe) into data/ and
evidence_store/, then re-verifies the restored chain.

    python scripts/restore.py <archive.tar.gz> [--dest DIR] [--force]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from olivechain import Ledger, Registry
from olivechain.backup import read_manifest, restore_backup

ap = argparse.ArgumentParser(description="Restore an OliveChain backup archive.")
ap.add_argument("archive", help="path to a .tar.gz backup")
ap.add_argument("--dest", default=".", help="destination project dir (default: .)")
ap.add_argument("--force", action="store_true", help="overwrite an existing ledger")
args = ap.parse_args()

with open(args.archive, "rb") as f:
    archive = f.read()

manifest = read_manifest(archive)
print(f"Archive: {manifest.get('format')}, exported_at={manifest.get('exported_at')}, "
      f"height={manifest.get('height')}, chain_valid={manifest.get('chain_valid')}, "
      f"evidence={manifest.get('evidence_count')}")

existing = os.path.join(args.dest, "data", "ledger.jsonl")
if os.path.exists(existing) and not args.force:
    sys.exit(f"Refusing to overwrite existing {existing} — pass --force to proceed.")

restore_backup(archive, args.dest)
print("Files restored and checksums verified.")

# re-verify the restored chain
ledger = Ledger(Registry(os.path.join(args.dest, "data", "registry.json")),
                os.path.join(args.dest, "data", "ledger.jsonl"))
ok, problems = ledger.verify_chain()
print(f"Restored chain: valid={ok}, height={len(ledger)}")
if not ok:
    for p in problems[:5]:
        print("  ", p)
    sys.exit(1)
