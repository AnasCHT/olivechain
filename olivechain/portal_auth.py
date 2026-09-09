"""Application users and signed sessions for the Fabric actor portal.

Each human user has an application username/password and a unique Fabric client
identity on the machine owned by their organization. The browser receives only
an HTTP-only application session; Fabric certificates and private keys remain
on the organization's Gateway Agent host.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path


PBKDF2_ITERATIONS = 310_000
SESSION_VERSION = 2
STORE_VERSION = 2
_USERNAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{2,63}")

PORTAL_IDENTITIES: dict[str, dict] = {
    "farmer-org": {
        "name": "Farmer Cooperative",
        "msp_id": "FarmerOrgMSP",
        "machine": "machine1",
        "roles": ["farmer"],
    },
    "maker-org": {
        "name": "Olive Mill",
        "msp_id": "MakerOrgMSP",
        "machine": "machine2",
        "roles": ["mill", "laboratory", "bottler"],
    },
    "courier-org": {
        "name": "Green Logistics",
        "msp_id": "CourierOrgMSP",
        "machine": "machine3",
        "roles": ["collector", "distributor", "retailer"],
    },
    "recycler-org": {
        "name": "BioEnergy Recovery",
        "msp_id": "RecyclerOrgMSP",
        "machine": "machine4",
        "roles": ["processor"],
    },
}


class PortalAuthError(Exception):
    pass


@dataclass(frozen=True)
class PortalSession:
    username: str
    display_name: str
    org_id: str
    org_name: str
    msp_id: str
    role: str
    identity_alias: str
    client_id_hash: str
    issued_at: int
    expires_at: int
    csrf_token: str

    def public_dict(self) -> dict:
        return {
            "authenticated": True,
            "username": self.username,
            "display_name": self.display_name,
            "org_id": self.org_id,
            "org_name": self.org_name,
            "msp_id": self.msp_id,
            "role": self.role,
            "identity_alias": self.identity_alias,
            "client_id_hash": self.client_id_hash,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "csrf_token": self.csrf_token,
        }


class PortalAuth:
    """Password store and stateless HMAC-signed user sessions."""

    def __init__(
        self,
        users_path: str | os.PathLike = "data/portal_users.json",
        secret_path: str | os.PathLike = "data/portal_session_secret",
        session_ttl_seconds: int | None = None,
    ):
        self.users_path = Path(users_path)
        self.secret_path = Path(secret_path)
        self.session_ttl_seconds = session_ttl_seconds or int(
            os.environ.get("OLIVECHAIN_PORTAL_SESSION_TTL_S", "28800")
        )
        self.cookie_name = os.environ.get(
            "OLIVECHAIN_PORTAL_COOKIE_NAME", "olivechain_portal_session"
        )
        self.cookie_secure = os.environ.get(
            "OLIVECHAIN_PORTAL_COOKIE_SECURE", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._lock = threading.RLock()
        self._secret = self._load_or_create_secret()

    # --------------------------------------------------------- public options
    def list_options(self) -> list[dict]:
        return [
            {
                "org_id": org_id,
                "name": spec["name"],
                "msp_id": spec["msp_id"],
                "machine": spec["machine"],
                "roles": list(spec["roles"]),
            }
            for org_id, spec in PORTAL_IDENTITIES.items()
        ]

    # ------------------------------------------------------------- user store
    def configured(self, org_id: str, role: str) -> bool:
        return any(
            row["org_id"] == org_id and row["role"] == role and row.get("active", True)
            for row in self._users().values()
        )

    def list_users(self, org_id: str | None = None) -> list[dict]:
        rows = []
        for row in self._users().values():
            if org_id is not None and row["org_id"] != org_id:
                continue
            rows.append(self._public_user(row))
        return sorted(rows, key=lambda row: (row["org_id"], row["role"], row["username"]))

    def get_user(self, username: str, *, require_active: bool = False) -> dict:
        key = self.normalize_username(username)
        row = self._users().get(key)
        if row is None:
            raise PortalAuthError("unknown user")
        if require_active and not row.get("active", True):
            raise PortalAuthError("user is disabled")
        return dict(row)

    def add_user(
        self,
        *,
        username: str,
        display_name: str,
        org_id: str,
        role: str,
        password: str,
        identity_alias: str,
        client_id_hash: str = "",
        created_by: str = "system",
    ) -> dict:
        username = self.normalize_username(username)
        spec = self.validate_identity(org_id, role)
        self._validate_password(password)
        display_name = display_name.strip()
        if not display_name or len(display_name) > 120:
            raise PortalAuthError("display_name is required (max 120 characters)")
        if not identity_alias or len(identity_alias) > 160:
            raise PortalAuthError("identity_alias is required")
        salt, digest = self._password_digest(password)
        now = int(time.time())
        with self._lock:
            store = self._load_store_unlocked()
            if username in store["users"]:
                raise PortalAuthError(f"username {username!r} already exists")
            store["users"][username] = {
                "username": username,
                "display_name": display_name,
                "org_id": org_id,
                "org_name": spec["name"],
                "msp_id": spec["msp_id"],
                "role": role,
                "identity_alias": identity_alias,
                "client_id_hash": client_id_hash,
                "active": True,
                "salt": self._b64(salt),
                "digest": self._b64(digest),
                "iterations": PBKDF2_ITERATIONS,
                "created_at": now,
                "updated_at": now,
                "created_by": created_by,
            }
            self._write_store_unlocked(store)
            return self._public_user(store["users"][username])

    def add_bootstrap_admin(
        self, org_id: str, username: str, display_name: str, password: str
    ) -> dict:
        return self.add_user(
            username=username,
            display_name=display_name,
            org_id=org_id,
            role="orgadmin",
            password=password,
            identity_alias="orgadmin",
            created_by="bootstrap",
        )

    def set_user_password(self, username: str, password: str) -> None:
        username = self.normalize_username(username)
        self._validate_password(password)
        salt, digest = self._password_digest(password)
        with self._lock:
            store = self._load_store_unlocked()
            row = store["users"].get(username)
            if row is None:
                raise PortalAuthError("unknown user")
            row["salt"] = self._b64(salt)
            row["digest"] = self._b64(digest)
            row["iterations"] = PBKDF2_ITERATIONS
            row["updated_at"] = int(time.time())
            self._write_store_unlocked(store)

    def set_user_status(self, username: str, active: bool) -> dict:
        username = self.normalize_username(username)
        with self._lock:
            store = self._load_store_unlocked()
            row = store["users"].get(username)
            if row is None:
                raise PortalAuthError("unknown user")
            row["active"] = bool(active)
            row["updated_at"] = int(time.time())
            self._write_store_unlocked(store)
            return self._public_user(row)

    # Backward-compatible helpers used by the 0.4 CLI/tests. They create one
    # legacy username per role and route to the original static agent alias.
    def set_password(self, *args) -> None:
        if len(args) == 2:
            username, password = args
            self.set_user_password(username, password)
            return
        if len(args) != 3:
            raise TypeError("set_password expects username,password or org_id,role,password")
        org_id, role, password = args
        username = self.normalize_username(str(role))
        if username in self._users():
            self.set_user_password(username, password)
            return
        self.add_user(
            username=username,
            display_name=str(role).replace("_", " ").title(),
            org_id=str(org_id),
            role=str(role),
            password=str(password),
            identity_alias=str(role),
            created_by="legacy-role-password",
        )

    def delete_password(self, org_id: str, role: str) -> bool:
        username = self.normalize_username(role)
        with self._lock:
            store = self._load_store_unlocked()
            row = store["users"].get(username)
            if row is None or row["org_id"] != org_id or row["role"] != role:
                return False
            del store["users"][username]
            self._write_store_unlocked(store)
            return True

    def authenticate(self, *args):
        if len(args) == 2:
            username, password = args
            return self._authenticate_user(str(username), str(password))
        if len(args) == 3:
            org_id, role, password = args
            try:
                row = self._authenticate_user(str(role), str(password))
            except PortalAuthError:
                return False
            return row["org_id"] == org_id and row["role"] == role
        raise TypeError("authenticate expects username,password or org_id,role,password")

    def _authenticate_user(self, username: str, password: str) -> dict:
        try:
            username = self.normalize_username(username)
        except PortalAuthError:
            username = "invalid-user"
        row = self._users().get(username)
        if not row:
            salt = b"\0" * 16
            expected = b"\0" * 32
            iterations = PBKDF2_ITERATIONS
        else:
            salt = self._unb64(row["salt"])
            expected = self._unb64(row["digest"])
            iterations = int(row.get("iterations", PBKDF2_ITERATIONS))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        if not row or not hmac.compare_digest(expected, actual):
            raise PortalAuthError("invalid username or password")
        if not row.get("active", True):
            raise PortalAuthError("user is disabled")
        return dict(row)

    # --------------------------------------------------------------- sessions
    def create_session(self, user_or_org, role: str | None = None) -> tuple[str, PortalSession]:
        if isinstance(user_or_org, dict):
            user = user_or_org
        elif role is not None:
            candidates = [
                row for row in self._users().values()
                if row["org_id"] == user_or_org and row["role"] == role and row.get("active", True)
            ]
            if not candidates:
                raise PortalAuthError("no active user configured for organization and role")
            user = candidates[0]
        else:
            user = self.get_user(str(user_or_org), require_active=True)
        now = int(time.time())
        session = PortalSession(
            username=user["username"],
            display_name=user["display_name"],
            org_id=user["org_id"],
            org_name=user.get("org_name") or PORTAL_IDENTITIES[user["org_id"]]["name"],
            msp_id=user.get("msp_id") or PORTAL_IDENTITIES[user["org_id"]]["msp_id"],
            role=user["role"],
            identity_alias=user["identity_alias"],
            client_id_hash=user.get("client_id_hash", ""),
            issued_at=now,
            expires_at=now + self.session_ttl_seconds,
            csrf_token=secrets.token_urlsafe(24),
        )
        payload = {
            "v": SESSION_VERSION,
            "username": session.username,
            "iat": session.issued_at,
            "exp": session.expires_at,
            "csrf": session.csrf_token,
            "nonce": secrets.token_urlsafe(12),
        }
        encoded = self._b64url(json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8"))
        signature = self._b64url(hmac.new(
            self._secret, encoded.encode("ascii"), hashlib.sha256
        ).digest())
        return f"{encoded}.{signature}", session

    def parse_session(self, token: str | None) -> PortalSession | None:
        if not token or "." not in token:
            return None
        encoded, supplied = token.split(".", 1)
        expected = self._b64url(hmac.new(
            self._secret, encoded.encode("ascii"), hashlib.sha256
        ).digest())
        if not hmac.compare_digest(expected, supplied):
            return None
        try:
            payload = json.loads(self._unb64url(encoded).decode("utf-8"))
            if payload.get("v") != SESSION_VERSION:
                return None
            now = int(time.time())
            issued = int(payload["iat"])
            expires = int(payload["exp"])
            if issued > now + 60 or expires <= now:
                return None
            user = self.get_user(str(payload["username"]), require_active=True)
            csrf = str(payload["csrf"])
            if len(csrf) < 20:
                return None
            return PortalSession(
                username=user["username"],
                display_name=user["display_name"],
                org_id=user["org_id"],
                org_name=user.get("org_name") or PORTAL_IDENTITIES[user["org_id"]]["name"],
                msp_id=user.get("msp_id") or PORTAL_IDENTITIES[user["org_id"]]["msp_id"],
                role=user["role"],
                identity_alias=user["identity_alias"],
                client_id_hash=user.get("client_id_hash", ""),
                issued_at=issued,
                expires_at=expires,
                csrf_token=csrf,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, PortalAuthError):
            return None

    def validate_csrf(self, session: PortalSession, supplied: str | None) -> bool:
        return bool(supplied) and hmac.compare_digest(session.csrf_token, supplied)

    # --------------------------------------------------------------- helpers
    def validate_identity(self, org_id: str, role: str) -> dict:
        spec = PORTAL_IDENTITIES.get(org_id)
        allowed = set(spec["roles"]) | {"orgadmin"} if spec else set()
        if not spec or role not in allowed:
            raise PortalAuthError("unknown organization or role")
        return spec

    @staticmethod
    def normalize_username(username: str) -> str:
        value = username.strip().lower()
        if not _USERNAME_RE.fullmatch(value):
            raise PortalAuthError(
                "username must be 3-64 lowercase letters, digits, hyphens or underscores"
            )
        return value

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < 10:
            raise PortalAuthError("password must contain at least 10 characters")
        if len(password) > 256:
            raise PortalAuthError("password is too long")

    @staticmethod
    def _password_digest(password: str) -> tuple[bytes, bytes]:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
        )
        return salt, digest

    def _users(self) -> dict:
        with self._lock:
            return dict(self._load_store_unlocked()["users"])

    def _load_store_unlocked(self) -> dict:
        if not self.users_path.exists():
            return {"schema_version": STORE_VERSION, "users": {}}
        try:
            data = json.loads(self.users_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise PortalAuthError(f"cannot read portal user store: {exc}") from exc
        if isinstance(data, dict) and data.get("schema_version") == STORE_VERSION:
            users = data.get("users")
            if not isinstance(users, dict):
                raise PortalAuthError("portal users must be a JSON object")
            return data
        if not isinstance(data, dict):
            raise PortalAuthError("portal user store must be a JSON object")
        migrated = self._migrate_legacy(data)
        self._write_store_unlocked(migrated)
        return migrated

    def _migrate_legacy(self, legacy: dict) -> dict:
        users: dict[str, dict] = {}
        now = int(time.time())
        for old_key, row in legacy.items():
            if not isinstance(row, dict):
                continue
            org_id = str(row.get("org_id") or old_key.partition(":")[0])
            role = str(row.get("role") or old_key.partition(":")[2])
            if org_id not in PORTAL_IDENTITIES or role not in PORTAL_IDENTITIES[org_id]["roles"]:
                continue
            username = self.normalize_username(role)
            users[username] = {
                "username": username,
                "display_name": role.replace("_", " ").title(),
                "org_id": org_id,
                "org_name": PORTAL_IDENTITIES[org_id]["name"],
                "msp_id": PORTAL_IDENTITIES[org_id]["msp_id"],
                "role": role,
                "identity_alias": role,
                "client_id_hash": "",
                "active": True,
                "salt": row["salt"],
                "digest": row["digest"],
                "iterations": int(row.get("iterations", PBKDF2_ITERATIONS)),
                "created_at": int(row.get("updated_at", now)),
                "updated_at": now,
                "created_by": "automatic-0.4-migration",
            }
        return {"schema_version": STORE_VERSION, "users": users}

    def _write_store_unlocked(self, store: dict) -> None:
        self.users_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.users_path.with_suffix(self.users_path.suffix + ".tmp")
        tmp.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.users_path)

    @staticmethod
    def _public_user(row: dict) -> dict:
        return {
            "username": row["username"],
            "display_name": row["display_name"],
            "org_id": row["org_id"],
            "org_name": row.get("org_name", ""),
            "msp_id": row.get("msp_id", ""),
            "role": row["role"],
            "identity_alias": row["identity_alias"],
            "client_id_hash": row.get("client_id_hash", ""),
            "active": bool(row.get("active", True)),
            "created_at": int(row.get("created_at", 0)),
            "updated_at": int(row.get("updated_at", 0)),
            "created_by": row.get("created_by", ""),
        }

    def _load_or_create_secret(self) -> bytes:
        configured = os.environ.get("OLIVECHAIN_PORTAL_SESSION_SECRET", "").strip()
        if configured:
            return hashlib.sha256(configured.encode("utf-8")).digest()
        if self.secret_path.exists():
            raw = self.secret_path.read_text().strip()
            if len(raw) >= 32:
                return hashlib.sha256(raw.encode("utf-8")).digest()
        self.secret_path.parent.mkdir(parents=True, exist_ok=True)
        raw = secrets.token_urlsafe(48)
        self.secret_path.write_text(raw + "\n")
        os.chmod(self.secret_path, 0o600)
        return hashlib.sha256(raw.encode("utf-8")).digest()

    @staticmethod
    def _b64(value: bytes) -> str:
        return base64.b64encode(value).decode("ascii")

    @staticmethod
    def _unb64(value: str) -> bytes:
        return base64.b64decode(value.encode("ascii"), validate=True)

    @staticmethod
    def _b64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _unb64url(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
