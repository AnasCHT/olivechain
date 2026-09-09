"""Registry facade combining local browser-signing profiles with Fabric MSP orgs."""
from __future__ import annotations

import threading
import time

from .fabric_client import FabricAgentRouter, FabricAgentError
from .models import Role
from .registry import Organization, PermissionError_, Registry


class FabricRegistry:
    """Preserves Registry's interface while exposing on-chain consortium orgs.

    Local registrations remain application-level actor profiles used for the
    existing browser Ed25519 signing flow. Fabric MSP organizations are loaded
    read-only from chaincode and provide the consortium/network view.
    """

    def __init__(self, local: Registry, router: FabricAgentRouter, cache_seconds: float = 5.0):
        self.local = local
        self.router = router
        self.path = local.path
        self.cache_seconds = cache_seconds
        self._fabric_orgs: dict[str, Organization] = {}
        self._loaded_at = 0.0
        self._lock = threading.Lock()

    def register(self, org_id: str, name: str, roles: list[Role], metadata: dict | None = None):
        return self.local.register(org_id, name, roles, metadata)

    def get(self, org_id: str) -> Organization:
        try:
            return self.local.get(org_id)
        except PermissionError_:
            self._refresh()
            try:
                return self._fabric_orgs[org_id]
            except KeyError as exc:
                raise PermissionError_(f"unknown organization: {org_id}") from exc

    def all(self) -> list[Organization]:
        self._refresh()
        merged = {org.org_id: org for org in self._fabric_orgs.values()}
        merged.update({org.org_id: org for org in self.local.all()})
        return list(merged.values())

    def _refresh(self, force: bool = False):
        now = time.monotonic()
        if not force and now - self._loaded_at < self.cache_seconds:
            return
        with self._lock:
            if not force and time.monotonic() - self._loaded_at < self.cache_seconds:
                return
            try:
                rows = self.router.evaluate("GetOrganizations") or []
            except FabricAgentError:
                # The app can still start and expose local profiles while a
                # peer/agent is temporarily unavailable.
                self._loaded_at = time.monotonic()
                return
            orgs: dict[str, Organization] = {}
            for row in rows:
                roles = []
                for role_name in row.get("roles", []):
                    try:
                        roles.append(Role(role_name))
                    except ValueError:
                        continue
                org = Organization(
                    org_id=row["org_id"],
                    name=row.get("name", row["org_id"]),
                    roles=roles,
                    public_key="",
                    metadata={**row.get("metadata", {}), "msp_id": row.get("msp_id")},
                )
                orgs[org.org_id] = org
            self._fabric_orgs = orgs
            self._loaded_at = time.monotonic()
