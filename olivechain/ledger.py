"""Trust layer: append-only, hash-chained, signed event ledger.

Technology-neutral by design (document: "Hyperledger Fabric, IOTA/Move, or
another platform is an implementation choice"). This module provides the
properties the document actually requires of the ledger:

  - immutable ordering (each event commits the hash of its predecessor)
  - digital signatures and actor roles (Ed25519, verified on append and audit)
  - append-only event history (corrections supersede, never overwrite)
  - provenance relationships (subject ids: batches, residues, orgs)
  - transparent rule execution (rules run in code reviewable by all parties)

Persisted as a JSON-lines file so the chain itself is inspectable and can be
re-verified from disk — real transaction records, not browser local storage.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Iterator, Optional

from .crypto import canonical_json, sha256_hex, verify_signature
from .models import EventType, PERMISSIONS, REQUIRED_FIELDS
from .registry import Registry, PermissionError_


GENESIS_HASH = "0" * 64


@dataclass
class Event:
    event_id: str
    event_type: str
    subject_id: str            # batch id, residue id, or org id the event is about
    actor_org: str             # authenticated organization id
    timestamp: float
    payload: dict
    actor_user: str = ""         # application username / wallet address
    actor_wallet: str = ""       # OliveChain wallet bound to the Fabric certificate
    evidence: list[dict] = field(default_factory=list)  # [{name, sha256, uri}]
    prev_hash: str = GENESIS_HASH
    signature: str = ""        # signs the signing_body
    event_hash: str = ""       # hash over signed body + signature
    superseded_by: Optional[str] = None  # set in-memory when a correction lands

    def signing_body(self) -> bytes:
        body = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "subject_id": self.subject_id,
            "actor_org": self.actor_org,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "evidence": self.evidence,
            "prev_hash": self.prev_hash,
        }
        return canonical_json(body)


class LedgerError(Exception):
    pass


class Ledger:
    def __init__(self, registry: Registry, path: str | None = None):
        self.registry = registry
        self.path = path
        self._events: list[Event] = []
        self._by_id: dict[str, Event] = {}
        if path and os.path.exists(path):
            self._load()

    # ------------------------------------------------------------- append
    def append(
        self,
        event_type: EventType,
        subject_id: str,
        actor_org: str,
        payload: dict,
        keypair,
        evidence: list[dict] | None = None,
        timestamp: float | None = None,
    ) -> Event:
        org = self.registry.get(actor_org)

        # role-based permission check
        allowed = PERMISSIONS[event_type]
        if not any(r in allowed for r in org.roles):
            raise PermissionError_(
                f"{actor_org} (roles={[r.value for r in org.roles]}) may not submit {event_type.value}"
            )

        # schema check
        missing = [f for f in REQUIRED_FIELDS[event_type] if f not in payload]
        if missing:
            raise LedgerError(f"{event_type.value}: missing required fields {missing}")

        ev = Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type.value,
            subject_id=subject_id,
            actor_org=actor_org,
            timestamp=timestamp if timestamp is not None else time.time(),
            payload=payload,
            evidence=evidence or [],
            prev_hash=self._events[-1].event_hash if self._events else GENESIS_HASH,
        )
        body = ev.signing_body()
        ev.signature = keypair.sign(body)

        # verify against the registered public key: the submitted key must
        # actually belong to the claimed organization
        if not verify_signature(org.public_key, body, ev.signature):
            raise LedgerError(f"signature does not match registered key of {actor_org}")

        ev.event_hash = sha256_hex(body + ev.signature.encode())

        # corrections supersede but never delete (audit trail preserved)
        if event_type is EventType.CORRECTION:
            target = self._by_id.get(payload["supersedes_event"])
            if target is None:
                raise LedgerError("correction targets unknown event")
            if target.actor_org != actor_org and not org.has_role_name("authority"):
                raise PermissionError_("only the original actor or an authority may correct an event")
            target.superseded_by = ev.event_id

        self._events.append(ev)
        self._by_id[ev.event_id] = ev
        if self.path:
            with open(self.path, "a") as f:
                f.write(json.dumps(asdict(ev)) + "\n")
        return ev


    def commit_prepared(self, body: dict, signature: str) -> Event:
        """Commit a body produced by the existing two-phase browser flow.

        FabricLedger implements the same method, allowing api.py to preserve
        its public request/response format while changing only persistence.
        """
        try:
            event_type = EventType(body["event_type"])
        except (KeyError, ValueError) as exc:
            raise LedgerError("unknown event type") from exc
        org = self.registry.get(body["actor_org"])
        if not any(role in PERMISSIONS[event_type] for role in org.roles):
            raise PermissionError_(f"role not permitted to submit {event_type.value}")
        missing = [field for field in REQUIRED_FIELDS[event_type] if field not in body["payload"]]
        if missing:
            raise LedgerError(f"{event_type.value}: missing required fields {missing}")
        if body["event_id"] in self._by_id:
            raise LedgerError("event_id already on the ledger")
        head = self._events[-1].event_hash if self._events else GENESIS_HASH
        if body.get("prev_hash") != head:
            raise LedgerError("ledger advanced since prepare; call /events/prepare again")
        ev = Event(**body)
        ev.signature = signature
        ev.event_hash = sha256_hex(ev.signing_body() + ev.signature.encode())
        if event_type is EventType.CORRECTION:
            target = self._by_id.get(ev.payload.get("supersedes_event", ""))
            if target is None:
                raise LedgerError("correction targets unknown event")
            if target.actor_org != ev.actor_org and not org.has_role_name("authority"):
                raise PermissionError_("only the original actor or an authority may correct an event")
            target.superseded_by = ev.event_id
        self._events.append(ev)
        self._by_id[ev.event_id] = ev
        if self.path:
            with open(self.path, "a") as f:
                f.write(json.dumps(asdict(ev)) + "\n")
        return ev

    @property
    def head_hash(self) -> str:
        return self._events[-1].event_hash if self._events else GENESIS_HASH

    backend_name = "local"

    # ------------------------------------------------------------- queries
    def __len__(self) -> int:
        return len(self._events)

    def all(self) -> list[Event]:
        return list(self._events)

    def get(self, event_id: str) -> Event:
        return self._by_id[event_id]

    def for_subject(self, subject_id: str, include_superseded: bool = False) -> list[Event]:
        evs = [e for e in self._events if e.subject_id == subject_id]
        if not include_superseded:
            evs = [e for e in evs if e.superseded_by is None]
        return evs

    def effective_payload(self, event: Event) -> dict:
        """Payload after applying the latest correction chain."""
        cur = event
        while cur.superseded_by:
            corr = self._by_id[cur.superseded_by]
            merged = dict(cur.payload)
            merged.update(corr.payload.get("corrected_payload", {}))
            cur = Event(**{**asdict(corr), "payload": merged})  # walk further corrections
            cur.payload = merged
        return cur.payload if cur is not event else event.payload

    def iter_type(self, event_type: EventType) -> Iterator[Event]:
        return (e for e in self._events if e.event_type == event_type.value)

    # ------------------------------------------------------------- audit
    def verify_chain(self) -> tuple[bool, list[str]]:
        """Full audit: hash-chain continuity + every signature + key ownership."""
        problems: list[str] = []
        prev = GENESIS_HASH
        for i, ev in enumerate(self._events):
            if ev.prev_hash != prev:
                problems.append(f"event {i} ({ev.event_id}): broken hash chain")
            body = ev.signing_body()
            org = self.registry.get(ev.actor_org)
            if not verify_signature(org.public_key, body, ev.signature):
                problems.append(f"event {i} ({ev.event_id}): invalid signature")
            expected = sha256_hex(body + ev.signature.encode())
            if ev.event_hash != expected:
                problems.append(f"event {i} ({ev.event_id}): tampered content")
            prev = ev.event_hash
        return (len(problems) == 0, problems)

    # ------------------------------------------------------------- persistence
    def _load(self):
        with open(self.path) as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                ev = Event(**d)
                self._events.append(ev)
                self._by_id[ev.event_id] = ev
        # rebuild supersession pointers
        for ev in self._events:
            if ev.event_type == EventType.CORRECTION.value:
                tgt = self._by_id.get(ev.payload.get("supersedes_event", ""))
                if tgt:
                    tgt.superseded_by = ev.event_id
