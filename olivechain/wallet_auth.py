"""Passwordless OliveChain wallet authentication.

The browser owns an ECDSA P-256 wallet key. FastAPI never receives the private
key. Login is a one-time challenge signed by the wallet and verified against
the public key registered on Hyperledger Fabric.
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

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature


SESSION_VERSION = 3
WALLET_RE = re.compile(r"OLIVE-[A-F0-9]{24}")
PUBLIC_REQUEST_ROLES = {
    "farmer": {"label": "Farmer", "org_id": "farmer-org"},
    "collector": {"label": "Transporter", "org_id": "courier-org"},
    "distributor": {"label": "Distributor", "org_id": "courier-org"},
    "retailer": {"label": "Retailer", "org_id": "courier-org"},
}
RESTRICTED_ROLES = {
    "maker-org": ["mill", "laboratory", "bottler"],
    "recycler-org": ["processor"],
    "farmer-org": [],
    "courier-org": [],
}

ORG_NAMES = {
    "farmer-org": "Farmer Cooperative",
    "maker-org": "Olive Mill",
    "courier-org": "Green Logistics",
    "recycler-org": "BioEnergy Recovery",
}


class WalletAuthError(Exception):
    pass


@dataclass(frozen=True)
class WalletSession:
    wallet_address: str
    username: str
    display_name: str
    org_id: str
    org_name: str
    msp_id: str
    role: str
    role_status: str
    identity_alias: str
    client_id_hash: str
    issued_at: int
    expires_at: int
    csrf_token: str

    @property
    def operational(self) -> bool:
        return self.role_status == "active" and bool(self.org_id and self.identity_alias)

    def public_dict(self) -> dict:
        return {
            "authenticated": True,
            "wallet_address": self.wallet_address,
            "username": self.username,
            "display_name": self.display_name,
            "org_id": self.org_id,
            "org_name": self.org_name,
            "msp_id": self.msp_id,
            "role": self.role,
            "role_status": self.role_status,
            "identity_alias": self.identity_alias,
            "client_id_hash": self.client_id_hash,
            "operational": self.operational,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "csrf_token": self.csrf_token,
        }


class WalletAuth:
    def __init__(
        self,
        secret_path: str | os.PathLike = "data/wallet_session_secret",
        session_ttl_seconds: int | None = None,
        challenge_ttl_seconds: int = 120,
    ):
        self.secret_path = Path(secret_path)
        self.session_ttl_seconds = session_ttl_seconds or int(
            os.environ.get("OLIVECHAIN_WALLET_SESSION_TTL_S", "28800")
        )
        self.challenge_ttl_seconds = challenge_ttl_seconds
        self.cookie_name = os.environ.get(
            "OLIVECHAIN_WALLET_COOKIE_NAME", "olivechain_wallet_session"
        )
        self.cookie_secure = os.environ.get(
            "OLIVECHAIN_WALLET_COOKIE_SECURE", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._secret = self._load_or_create_secret()
        self._challenges: dict[str, dict] = {}
        self._lock = threading.RLock()

    @staticmethod
    def expected_address(public_key_spki_b64: str) -> str:
        try:
            raw = base64.b64decode(public_key_spki_b64.encode("ascii"), validate=True)
        except Exception as exc:
            raise WalletAuthError("wallet public key is not valid base64") from exc
        if len(raw) < 32:
            raise WalletAuthError("wallet public key is too short")
        digest = hashlib.sha256(raw).hexdigest()[:24].upper()
        return f"OLIVE-{digest}"

    @staticmethod
    def validate_address(address: str) -> str:
        value = address.strip().upper()
        if not WALLET_RE.fullmatch(value):
            raise WalletAuthError("invalid OliveChain wallet address")
        return value

    def issue_challenge(self, wallet_address: str, purpose: str = "login") -> dict:
        address = self.validate_address(wallet_address)
        purpose = purpose.strip().lower()
        if purpose not in {"login", "register"}:
            raise WalletAuthError("invalid wallet challenge purpose")
        now = int(time.time())
        nonce = secrets.token_urlsafe(32)
        label = "registration" if purpose == "register" else "authentication"
        message = (
            f"OliveChain wallet {label}\n"
            f"purpose={purpose}\n"
            f"wallet={address}\n"
            f"nonce={nonce}\n"
            f"issued_at={now}"
        )
        with self._lock:
            self._purge_challenges(now)
            self._challenges[address] = {
                "message": message,
                "purpose": purpose,
                "expires_at": now + self.challenge_ttl_seconds,
            }
        return {
            "wallet_address": address,
            "message": message,
            "purpose": purpose,
            "expires_at": now + self.challenge_ttl_seconds,
        }

    def verify_challenge(
        self,
        wallet_address: str,
        public_key_spki_b64: str,
        signature_b64url: str,
        purpose: str = "login",
    ) -> None:
        address = self.validate_address(wallet_address)
        if self.expected_address(public_key_spki_b64) != address:
            raise WalletAuthError("wallet address does not match public key")
        with self._lock:
            now = int(time.time())
            self._purge_challenges(now)
            challenge = self._challenges.pop(address, None)
        if not challenge:
            raise WalletAuthError("wallet challenge is missing or expired")
        if challenge.get("purpose") != purpose:
            raise WalletAuthError("wallet challenge purpose does not match")
        try:
            public_der = base64.b64decode(public_key_spki_b64.encode("ascii"), validate=True)
            public_key = serialization.load_der_public_key(public_der)
        except Exception as exc:
            raise WalletAuthError("wallet public key cannot be decoded") from exc
        if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(
            public_key.curve, ec.SECP256R1
        ):
            raise WalletAuthError("wallet must use ECDSA P-256")
        try:
            signature = self._unb64url(signature_b64url)
        except Exception as exc:
            raise WalletAuthError("wallet signature is not valid base64url") from exc
        # WebCrypto returns an IEEE-P1363 r||s signature for ECDSA. Python's
        # cryptography verifier expects ASN.1 DER, so convert the 64-byte form.
        if len(signature) == 64:
            r = int.from_bytes(signature[:32], "big")
            s = int.from_bytes(signature[32:], "big")
            signature = encode_dss_signature(r, s)
        try:
            public_key.verify(
                signature,
                challenge["message"].encode("utf-8"),
                ec.ECDSA(hashes.SHA256()),
            )
        except InvalidSignature as exc:
            raise WalletAuthError("wallet signature is invalid") from exc

    def create_session(self, wallet: dict) -> tuple[str, WalletSession]:
        now = int(time.time())
        session = self._session_from_wallet(
            wallet, now, now + self.session_ttl_seconds, secrets.token_urlsafe(24)
        )
        payload = {
            "v": SESSION_VERSION,
            "wallet": session.wallet_address,
            "iat": session.issued_at,
            "exp": session.expires_at,
            "csrf": session.csrf_token,
            "nonce": secrets.token_urlsafe(12),
        }
        encoded = self._b64url(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        signature = self._b64url(
            hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        )
        return f"{encoded}.{signature}", session

    def parse_session(self, token: str | None, wallet_lookup) -> WalletSession | None:
        if not token or "." not in token:
            return None
        encoded, supplied = token.split(".", 1)
        expected = self._b64url(
            hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        )
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
            address = self.validate_address(str(payload["wallet"]))
            wallet = wallet_lookup(address)
            if not wallet or wallet.get("status") != "active":
                return None
            csrf = str(payload["csrf"])
            if len(csrf) < 20:
                return None
            return self._session_from_wallet(wallet, issued, expires, csrf)
        except Exception:
            return None

    @staticmethod
    def validate_csrf(session: WalletSession, supplied: str | None) -> bool:
        return bool(supplied) and hmac.compare_digest(session.csrf_token, supplied)

    def _session_from_wallet(
        self, wallet: dict, issued_at: int, expires_at: int, csrf_token: str
    ) -> WalletSession:
        role_status = str(wallet.get("role_status") or "consumer")
        role = str(wallet.get("role") or "consumer")
        org_id = str(wallet.get("org_id") or "") if role_status == "active" else ""
        msp_id = str(wallet.get("msp_id") or "") if role_status == "active" else ""
        identity_alias = (
            str(wallet.get("identity_alias") or "") if role_status == "active" else ""
        )
        client_id_hash = (
            str(wallet.get("client_id_hash") or "") if role_status == "active" else ""
        )
        if role_status != "active":
            role = "consumer"
        address = self.validate_address(str(wallet["wallet_address"]))
        return WalletSession(
            wallet_address=address,
            username=address,
            display_name=str(wallet.get("display_name") or address),
            org_id=org_id,
            org_name=ORG_NAMES.get(org_id, "Consumer / Unassigned"),
            msp_id=msp_id,
            role=role,
            role_status=role_status,
            identity_alias=identity_alias,
            client_id_hash=client_id_hash,
            issued_at=issued_at,
            expires_at=expires_at,
            csrf_token=csrf_token,
        )

    def _purge_challenges(self, now: int) -> None:
        for key in list(self._challenges):
            if int(self._challenges[key]["expires_at"]) <= now:
                self._challenges.pop(key, None)

    def _load_or_create_secret(self) -> bytes:
        configured = os.environ.get("OLIVECHAIN_WALLET_SESSION_SECRET", "").strip()
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
    def _b64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _unb64url(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
