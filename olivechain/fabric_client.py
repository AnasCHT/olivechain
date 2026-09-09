"""HTTP client and router for per-organization Fabric Gateway Agents."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable


class FabricAgentError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentTarget:
    url: str
    identity: str


_ROLE_AGENT_ENV = {
    "farmer": "OLIVECHAIN_AGENT_URL_FARMER",
    "mill": "OLIVECHAIN_AGENT_URL_MAKER",
    "laboratory": "OLIVECHAIN_AGENT_URL_MAKER",
    "bottler": "OLIVECHAIN_AGENT_URL_MAKER",
    "collector": "OLIVECHAIN_AGENT_URL_COURIER",
    "distributor": "OLIVECHAIN_AGENT_URL_COURIER",
    "retailer": "OLIVECHAIN_AGENT_URL_COURIER",
    "consumer": "OLIVECHAIN_AGENT_URL_COURIER",
    "processor": "OLIVECHAIN_AGENT_URL_RECYCLER",
    "orgadmin": "OLIVECHAIN_AGENT_URL_FARMER",
}

_IDENTITY_ALIAS = {
    "farmer": "farmer",
    "mill": "mill",
    "laboratory": "laboratory",
    "bottler": "bottler",
    "collector": "collector",
    "distributor": "distributor",
    "retailer": "retailer",
    "consumer": "consumer",
    "processor": "processor",
    "orgadmin": "orgadmin",
}

_ORG_AGENT_ENV = {
    "farmer-org": "OLIVECHAIN_AGENT_URL_FARMER",
    "maker-org": "OLIVECHAIN_AGENT_URL_MAKER",
    "courier-org": "OLIVECHAIN_AGENT_URL_COURIER",
    "recycler-org": "OLIVECHAIN_AGENT_URL_RECYCLER",
}


class FabricAgentRouter:
    """Routes calls while keeping every signing identity on its owning host."""

    def __init__(
        self,
        token: str,
        role_targets: dict[str, AgentTarget],
        org_urls: dict[str, str],
        timeout: float = 30.0,
    ):
        if not token:
            raise ValueError("OLIVECHAIN_AGENT_TOKEN is required")
        self.token = token
        self.role_targets = role_targets
        self.org_urls = {key: value.rstrip("/") for key, value in org_urls.items()}
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "FabricAgentRouter":
        token = os.environ.get("OLIVECHAIN_AGENT_TOKEN", "")
        defaults = {
            "OLIVECHAIN_AGENT_URL_FARMER": "http://127.0.0.1:9080",
            "OLIVECHAIN_AGENT_URL_MAKER": "http://127.0.0.1:9081",
            "OLIVECHAIN_AGENT_URL_COURIER": "http://127.0.0.1:9082",
            "OLIVECHAIN_AGENT_URL_RECYCLER": "http://127.0.0.1:9083",
        }
        role_targets: dict[str, AgentTarget] = {}
        for role, env_name in _ROLE_AGENT_ENV.items():
            url = os.environ.get(env_name, defaults[env_name]).rstrip("/")
            role_targets[role] = AgentTarget(url=url, identity=_IDENTITY_ALIAS[role])
        org_urls = {
            org_id: os.environ.get(env_name, defaults[env_name]).rstrip("/")
            for org_id, env_name in _ORG_AGENT_ENV.items()
        }
        timeout = float(os.environ.get("OLIVECHAIN_AGENT_TIMEOUT_S", "30"))
        return cls(token=token, role_targets=role_targets, org_urls=org_urls, timeout=timeout)

    def target_for_role(self, role: str) -> AgentTarget:
        try:
            return self.role_targets[role]
        except KeyError as exc:
            raise FabricAgentError(f"no Fabric Gateway agent configured for role {role!r}") from exc

    def url_for_org(self, org_id: str) -> str:
        try:
            return self.org_urls[org_id]
        except KeyError as exc:
            raise FabricAgentError(f"no Fabric Gateway agent configured for organization {org_id!r}") from exc

    def evaluate(self, transaction: str, args: Iterable[str] = (), role: str = "farmer"):
        target = self.target_for_role(role)
        return self._call_url(target.url, "evaluate", target.identity, transaction, args)

    def submit(self, role: str, transaction: str, args: Iterable[str] = ()):
        target = self.target_for_role(role)
        return self._call_url(target.url, "submit", target.identity, transaction, args)

    def evaluate_as(
        self, org_id: str, identity: str, transaction: str, args: Iterable[str] = ()
    ):
        return self._call_url(self.url_for_org(org_id), "evaluate", identity, transaction, args)

    def submit_as(
        self, org_id: str, identity: str, transaction: str, args: Iterable[str] = ()
    ):
        return self._call_url(self.url_for_org(org_id), "submit", identity, transaction, args)

    def health(self, role: str = "farmer") -> dict:
        return self._health_url(self.target_for_role(role).url)

    def health_for_org(self, org_id: str) -> dict:
        return self._health_url(self.url_for_org(org_id))

    def create_identity(
        self, org_id: str, username: str, display_name: str, role: str,
        wallet_address: str = "",
    ) -> dict:
        return self._admin_call(org_id, "/admin/identities", {
            "username": username,
            "display_name": display_name,
            "role": role,
            "wallet_address": wallet_address,
        })

    def set_identity_status(self, org_id: str, identity_alias: str, active: bool) -> dict:
        return self._admin_call(org_id, "/admin/identities/status", {
            "identity_alias": identity_alias,
            "active": bool(active),
        })

    def list_identities(self, org_id: str) -> list[dict]:
        request = urllib.request.Request(
            self.url_for_org(org_id) + "/admin/identities",
            headers={"Authorization": f"Bearer {self.token}"},
            method="GET",
        )
        response = self._request_json(request)
        return list(response.get("identities") or [])

    def _health_url(self, url: str) -> dict:
        request = urllib.request.Request(
            url + "/health",
            headers={"Authorization": f"Bearer {self.token}"},
            method="GET",
        )
        return self._request_json(request)

    def _admin_call(self, org_id: str, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            self.url_for_org(org_id) + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        return self._request_json(request)

    def _call_url(
        self,
        url: str,
        operation: str,
        identity: str,
        transaction: str,
        args: Iterable[str],
    ):
        payload = json.dumps({
            "identity": identity,
            "transaction": transaction,
            "args": [str(arg) for arg in args],
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{url}/{operation}",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        response = self._request_json(request)
        return response.get("result")

    def _request_json(self, request: urllib.request.Request):
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise FabricAgentError(f"Gateway agent returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FabricAgentError(f"Gateway agent connection failed: {exc}") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FabricAgentError("Gateway agent returned malformed JSON") from exc
