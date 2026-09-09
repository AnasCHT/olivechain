"""Evidence layer: controlled off-chain storage + on-chain hash anchoring.

Document: "Not every data field belongs on-chain. Commercially sensitive
documents, personal information, large sensor streams, laboratory files, and
images should normally remain in controlled off-chain storage. The ledger
should retain ... a cryptographic hash or reference that makes later
substitution detectable."
"""
from __future__ import annotations

import os

from .crypto import sha256_hex


class EvidenceStore:
    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def put(self, name: str, data: bytes) -> dict:
        """Store an artifact; return the reference dict to embed in an event."""
        digest = sha256_hex(data)
        path = os.path.join(self.root, f"{digest}_{os.path.basename(name)}")
        with open(path, "wb") as f:
            f.write(data)
        return {"name": name, "sha256": digest, "uri": path}

    def verify(self, ref: dict) -> bool:
        """Detects later substitution of off-chain evidence."""
        try:
            with open(ref["uri"], "rb") as f:
                return sha256_hex(f.read()) == ref["sha256"]
        except FileNotFoundError:
            return False
