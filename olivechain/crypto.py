"""Cryptographic primitives for OliveChain.

Real Ed25519 signatures and SHA-256 hashing — no simulated verification.
Every ledger event is signed by the submitting organization's private key,
and every piece of off-chain evidence is anchored on-chain by its hash so
later substitution is detectable (document: "Trust architecture" /
"Evidence layer").
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj) -> bytes:
    """Deterministic serialization so hashes/signatures are reproducible."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass
class KeyPair:
    private_key: Ed25519PrivateKey

    @classmethod
    def generate(cls) -> "KeyPair":
        return cls(Ed25519PrivateKey.generate())

    @property
    def public_hex(self) -> str:
        raw = self.private_key.public_key().public_bytes_raw()
        return raw.hex()

    def sign(self, message: bytes) -> str:
        return self.private_key.sign(message).hex()

    @classmethod
    def from_private_hex(cls, hexkey: str) -> "KeyPair":
        return cls(Ed25519PrivateKey.from_private_bytes(bytes.fromhex(hexkey)))

    @property
    def private_hex(self) -> str:
        return self.private_key.private_bytes_raw().hex()


def verify_signature(public_hex: str, message: bytes, signature_hex: str) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex))
        pub.verify(bytes.fromhex(signature_hex), message)
        return True
    except (InvalidSignature, ValueError):
        return False
