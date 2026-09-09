"""Fabric-backed implementation of OliveChain's existing Ledger interface."""
from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Iterator

from .crypto import canonical_json, sha256_hex
from .fabric_client import FabricAgentError, FabricAgentRouter
from .ledger import Event, LedgerError, GENESIS_HASH
from .models import EventType, PERMISSIONS
from .registry import PermissionError_

_APP_META_KEY = "_olivechain_app"
_GOVERNANCE_TYPES = {
    EventType.REWARD_ISSUED,
    EventType.REVIEW_FLAG,
    EventType.REVIEW_RESOLUTION,
}


class FabricLedger:
    """Adapter preserving the methods consumed by the existing FastAPI app.

    Fabric supplies authoritative ordering and MSP signatures. The existing
    browser signature is retained inside a reserved payload envelope so the
    portal's user experience and actor-level accountability remain intact.
    """

    backend_name = "fabric"
    path = None

    def __init__(self, registry, router: FabricAgentRouter, cache_seconds: float = 0.75):
        self.registry = registry
        self.router = router
        self.cache_seconds = cache_seconds
        self._cache: list[Event] = []
        self._raw_by_id: dict[str, dict] = {}
        self._cache_time = 0.0
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return len(self.all())

    @property
    def head_hash(self) -> str:
        events = self.all()
        return events[-1].event_hash if events else GENESIS_HASH

    def all(self) -> list[Event]:
        with self._lock:
            if time.monotonic() - self._cache_time < self.cache_seconds:
                return list(self._cache)
            rows = self.router.evaluate("GetAllEvents", ["true"]) or []
            self._set_cache(rows)
            return list(self._cache)

    def get(self, event_id: str) -> Event:
        row = self.router.evaluate("GetEvent", [event_id])
        if not row:
            raise KeyError(event_id)
        return self._convert(row)

    def for_subject(self, subject_id: str, include_superseded: bool = False) -> list[Event]:
        rows = self.router.evaluate(
            "GetEventsForSubject",
            [subject_id, "true" if include_superseded else "false"],
        ) or []
        return [self._convert(row) for row in rows]


    def workflow_status(self, subject_id: str) -> dict:
        return self.router.evaluate("GetSubjectStatus", [subject_id]) or {}

    def workflow_statuses(self) -> list[dict]:
        return list(self.router.evaluate("GetWorkflowStatuses", []) or [])

    def workflow_definitions(self) -> list[dict]:
        return list(self.router.evaluate("GetWorkflowDefinitions", []) or [])


    # --------------------------------------------------------- wallet registry
    def register_wallet(self, wallet_address: str, public_key_spki: str, display_name: str) -> dict:
        return self.router.submit("consumer", "RegisterWallet", [wallet_address, public_key_spki, display_name]) or {}

    def get_wallet(self, wallet_address: str) -> dict:
        return self.router.evaluate("GetWallet", [wallet_address]) or {}

    def wallets(self) -> list[dict]:
        return list(self.router.evaluate("GetWallets", []) or [])

    def request_wallet_role(self, wallet_address: str, role: str) -> dict:
        return self.router.submit("consumer", "RequestWalletRole", [wallet_address, role]) or {}

    def wallet_role_requests(self, wallet_address: str) -> list[dict]:
        return list(self.router.evaluate("GetWalletRoleRequests", [wallet_address]) or [])

    def role_requests_for_org(self, org_id: str) -> list[dict]:
        return list(self.router.evaluate("GetRoleRequestsForOrg", [org_id]) or [])

    def get_role_request(self, request_id: str) -> dict:
        return self.router.evaluate("GetWalletRoleRequest", [request_id]) or {}

    def approve_wallet_role(self, org_id: str, admin_identity: str, request_id: str, client_id_hash: str, identity_alias: str) -> dict:
        return self.router.submit_as(org_id, admin_identity, "ApproveWalletRoleRequest", [request_id, client_id_hash, identity_alias]) or {}

    def reject_wallet_role(self, org_id: str, admin_identity: str, request_id: str, reason: str) -> dict:
        return self.router.submit_as(org_id, admin_identity, "RejectWalletRoleRequest", [request_id, reason]) or {}

    def grant_wallet_role(self, org_id: str, admin_identity: str, wallet_address: str, role: str, client_id_hash: str, identity_alias: str) -> dict:
        return self.router.submit_as(org_id, admin_identity, "GrantWalletRole", [wallet_address, role, client_id_hash, identity_alias]) or {}

    def revoke_wallet_role(self, org_id: str, admin_identity: str, wallet_address: str, reason: str) -> dict:
        return self.router.submit_as(org_id, admin_identity, "RevokeWalletRole", [wallet_address, reason]) or {}

    def wallet_assets(self, wallet_address: str) -> dict:
        return self.router.evaluate("GetWalletAssets", [wallet_address]) or {}

    def wallet_token_transactions(self, wallet_address: str) -> list[dict]:
        return list(self.router.evaluate("GetWalletTokenTransactions", [wallet_address]) or [])

    def token_transactions_for_subject(self, subject_id: str) -> list[dict]:
        return list(self.router.evaluate("GetTokenTransactionsForSubject", [subject_id]) or [])

    def token_policy(self) -> dict:
        return self.router.evaluate("GetTokenPolicy", []) or {}

    def effective_payload(self, event: Event) -> dict:
        row = self.router.evaluate("GetEffectiveEvent", [event.event_id])
        if not row:
            return event.payload
        return self._visible_payload(row.get("payload", {}))

    def iter_type(self, event_type: EventType) -> Iterator[Event]:
        rows = self.router.evaluate("GetEventsByType", [event_type.value, "true"]) or []
        return iter(self._convert(row) for row in rows)

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
        body = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type.value,
            "subject_id": subject_id,
            "actor_org": actor_org,
            "timestamp": timestamp if timestamp is not None else time.time(),
            "payload": payload,
            "evidence": evidence or [],
            "prev_hash": self.head_hash,
        }
        signature = keypair.sign(canonical_json(body))
        return self.commit_prepared(body, signature)

    def commit_prepared(
        self,
        body: dict,
        signature: str,
        role_override: str | None = None,
        identity_override: str | None = None,
        portal_user: dict | None = None,
    ) -> Event:
        try:
            event_type = EventType(body["event_type"])
        except (KeyError, ValueError) as exc:
            raise LedgerError("unknown event type") from exc
        if event_type in _GOVERNANCE_TYPES:
            raise LedgerError(
                f"{event_type.value} requires the three-organization governance workflow"
            )
        org = self.registry.get(body["actor_org"])
        role = self._submission_role(org.roles, event_type)
        if role_override is not None:
            available = {getattr(item, "value", str(item)) for item in org.roles}
            if role_override not in available:
                raise PermissionError_(
                    f"organization {body['actor_org']} does not provide role {role_override!r}"
                )
            allowed_names = {item.value for item in PERMISSIONS[event_type]}
            if role_override not in allowed_names:
                raise PermissionError_(
                    f"role {role_override!r} may not submit {event_type.value}"
                )
            role = role_override
        payload = dict(body["payload"])
        portal_user = portal_user or {}
        payload[_APP_META_KEY] = {
            "actor_org": body["actor_org"],
            "browser_signature": signature,
            "application_role": role,
            "portal_username": portal_user.get("username", ""),
            "portal_display_name": portal_user.get("display_name", ""),
            "wallet_address": portal_user.get("wallet_address", ""),
            "fabric_identity_alias": identity_override or "",
            "signed_body_sha256": sha256_hex(canonical_json(body)),
            "prepared_timestamp": body["timestamp"],
            "prepared_prev_hash": body.get("prev_hash", GENESIS_HASH),
        }
        evidence_json = json.dumps(body.get("evidence", []), separators=(",", ":"))
        if identity_override:
            submit = lambda transaction, args: self.router.submit_as(
                body["actor_org"], identity_override, transaction, args
            )
        else:
            submit = lambda transaction, args: self.router.submit(
                role, transaction, args
            )
        try:
            if event_type is EventType.CORRECTION:
                result = submit("CorrectEvent", [
                    body["event_id"],
                    payload["supersedes_event"],
                    payload["reason"],
                    json.dumps(payload["corrected_payload"], separators=(",", ":")),
                    evidence_json,
                ])
            else:
                result = submit("SubmitEvent", [
                    body["event_id"],
                    event_type.value,
                    body["subject_id"],
                    json.dumps(payload, separators=(",", ":")),
                    evidence_json,
                ])
        except FabricAgentError as exc:
            message = str(exc)
            try:
                if ": {" in message:
                    detail = json.loads(message[message.index("{"):])
                    message = detail.get("error") or message
            except (ValueError, json.JSONDecodeError):
                pass
            raise LedgerError(message) from exc
        if not result:
            raise LedgerError("Fabric transaction committed without an event response")
        self._invalidate()
        return self._convert(result)

    def verify_chain(self) -> tuple[bool, list[str]]:
        """Validate the chaincode event view returned by a validating peer.

        Block and endorsement validation are performed by Fabric peers before
        world-state commitment. Here we additionally check event identifiers,
        Fabric signatures markers, transaction IDs, and event hashes.
        """
        try:
            events = self.all()
        except FabricAgentError as exc:
            return False, [str(exc)]
        problems: list[str] = []
        seen: set[str] = set()
        for index, event in enumerate(events):
            raw = self._raw_by_id.get(event.event_id, {})
            if event.event_id in seen:
                problems.append(f"event {index} ({event.event_id}): duplicate id")
            seen.add(event.event_id)
            if not event.event_hash:
                problems.append(f"event {index} ({event.event_id}): missing event hash")
            if not raw.get("fabric_tx_id"):
                problems.append(f"event {index} ({event.event_id}): missing Fabric transaction id")
            if raw.get("signed_by_fabric") is not True:
                problems.append(f"event {index} ({event.event_id}): not marked as Fabric-signed")
        return not problems, problems

    def _submission_role(self, roles, event_type: EventType) -> str:
        allowed = PERMISSIONS[event_type]
        for role in roles:
            if role in allowed:
                return role.value
        role_names = [getattr(role, "value", str(role)) for role in roles]
        raise PermissionError_(
            f"roles {role_names} may not submit {event_type.value}"
        )

    def _invalidate(self):
        with self._lock:
            self._cache_time = 0.0

    def _set_cache(self, rows: list[dict]):
        self._raw_by_id = {row["event_id"]: row for row in rows}
        self._cache = [self._convert(row) for row in rows]
        self._cache_time = time.monotonic()

    def _convert(self, row: dict) -> Event:
        payload = dict(row.get("payload") or {})
        app_meta = payload.pop(_APP_META_KEY, {}) if isinstance(payload, dict) else {}
        actor_org = app_meta.get("actor_org") or row.get("actor_org") or row.get("actor_msp", "")
        signature = app_meta.get("browser_signature") or f"fabric:{row.get('client_id_hash', '')}"
        return Event(
            event_id=row["event_id"],
            event_type=row["event_type"],
            subject_id=row["subject_id"],
            actor_org=actor_org,
            timestamp=float(row.get("timestamp", 0)),
            payload=payload,
            actor_user=app_meta.get("portal_username", ""),
            actor_wallet=row.get("actor_wallet") or app_meta.get("wallet_address", ""),
            evidence=list(row.get("evidence") or []),
            prev_hash=app_meta.get("prepared_prev_hash", GENESIS_HASH),
            signature=signature,
            event_hash=row.get("event_hash", ""),
            superseded_by=row.get("superseded_by") or None,
        )

    @staticmethod
    def _visible_payload(payload: dict) -> dict:
        visible = dict(payload or {})
        visible.pop(_APP_META_KEY, None)
        return visible
