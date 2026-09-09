"""Identity layer: authenticated organizations, roles, and public keys.

Real organizational authentication (roadmap step 2: "remove exposed
credentials, simulated blockchain verification"): private keys are generated
per organization and never stored in the ledger; only public keys are
registered. In a production consortium this registry would be governed by
the authority/consortium body (an onboarding decision only the operating
consortium can make).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .crypto import KeyPair
from .models import Role


class PermissionError_(Exception):
    pass


@dataclass
class Organization:
    org_id: str
    name: str
    roles: list[Role]
    public_key: str
    metadata: dict = field(default_factory=dict)

    def has_role_name(self, name: str) -> bool:
        return any(r.value == name for r in self.roles)


class Registry:
    def __init__(self, path: str | None = None):
        self.path = path
        self._orgs: dict[str, Organization] = {}
        if path and os.path.exists(path):
            self._load()

    def register(self, org_id: str, name: str, roles: list[Role], metadata: dict | None = None) -> KeyPair:
        """Register an organization; returns its keypair (private key is
        handed to the org, not persisted by the registry)."""
        if org_id in self._orgs:
            raise ValueError(f"organization {org_id} already registered")
        kp = KeyPair.generate()
        self._orgs[org_id] = Organization(
            org_id=org_id, name=name, roles=roles,
            public_key=kp.public_hex, metadata=metadata or {},
        )
        self._save()
        return kp

    def get(self, org_id: str) -> Organization:
        if org_id not in self._orgs:
            raise PermissionError_(f"unknown organization: {org_id}")
        return self._orgs[org_id]

    def all(self) -> list[Organization]:
        return list(self._orgs.values())

    def _save(self):
        if not self.path:
            return
        with open(self.path, "w") as f:
            json.dump(
                {
                    oid: {
                        "name": o.name,
                        "roles": [r.value for r in o.roles],
                        "public_key": o.public_key,
                        "metadata": o.metadata,
                    }
                    for oid, o in self._orgs.items()
                },
                f, indent=2,
            )

    def _load(self):
        with open(self.path) as f:
            data = json.load(f)
        for oid, d in data.items():
            self._orgs[oid] = Organization(
                org_id=oid, name=d["name"],
                roles=[Role(r) for r in d["roles"]],
                public_key=d["public_key"], metadata=d.get("metadata", {}),
            )
