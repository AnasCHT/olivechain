"""OliveChain — a verifiable circular trust system for olive oil.

Reference implementation of the minimum viable trust chain (pilot stage 3):
batch identity, harvest and milling events, laboratory evidence, residue
generation, custody transfer, transformation confirmation, and a
consumer-facing passport — with real signatures and real hash chaining.
"""
from .registry import Registry
from .ledger import Ledger
from .evidence import EvidenceStore
from .incentives import IncentiveEngine
from .passport import build_passport
from .massbalance import reconcile_residue
from .models import Role, EventType

__all__ = [
    "Registry", "Ledger", "EvidenceStore", "IncentiveEngine",
    "build_passport", "reconcile_residue", "Role", "EventType",
]
__version__ = "0.1.0"
