import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from olivechain.wallet_auth import WalletAuth, WalletAuthError


def _wallet_material():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_b64 = base64.b64encode(public_der).decode("ascii")
    address = WalletAuth.expected_address(public_b64)
    return private_key, public_b64, address


def _raw_webcrypto_signature(private_key, message: str) -> str:
    der = private_key.sign(message.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def test_wallet_address_is_deterministic():
    _, public_b64, address = _wallet_material()
    assert address == WalletAuth.expected_address(public_b64)
    assert address.startswith("OLIVE-")
    assert len(address) == 30


def test_challenge_accepts_webcrypto_raw_signature(tmp_path):
    auth = WalletAuth(secret_path=tmp_path / "secret", challenge_ttl_seconds=60)
    private_key, public_b64, address = _wallet_material()
    challenge = auth.issue_challenge(address)
    signature = _raw_webcrypto_signature(private_key, challenge["message"])
    auth.verify_challenge(address, public_b64, signature)
    with pytest.raises(WalletAuthError, match="missing or expired"):
        auth.verify_challenge(address, public_b64, signature)


def test_challenge_rejects_wrong_key(tmp_path):
    auth = WalletAuth(secret_path=tmp_path / "secret")
    private_key, public_b64, address = _wallet_material()
    other_key, _, _ = _wallet_material()
    challenge = auth.issue_challenge(address)
    signature = _raw_webcrypto_signature(other_key, challenge["message"])
    with pytest.raises(WalletAuthError, match="invalid"):
        auth.verify_challenge(address, public_b64, signature)


def test_session_refreshes_wallet_role_state(tmp_path):
    auth = WalletAuth(secret_path=tmp_path / "secret")
    _, public_b64, address = _wallet_material()
    current = {
        "wallet_address": address,
        "public_key_spki": public_b64,
        "display_name": "Test Wallet",
        "status": "active",
        "role": "consumer",
        "role_status": "consumer",
        "org_id": "",
        "msp_id": "",
        "identity_alias": "",
        "client_id_hash": "",
    }
    token, session = auth.create_session(current)
    assert session.role == "consumer"
    assert not session.operational

    current.update({
        "role": "farmer",
        "role_status": "active",
        "org_id": "farmer-org",
        "msp_id": "FarmerOrgMSP",
        "identity_alias": "user:w-test",
        "client_id_hash": "abc123",
    })
    refreshed = auth.parse_session(token, lambda _: current)
    assert refreshed is not None
    assert refreshed.role == "farmer"
    assert refreshed.operational
    assert refreshed.identity_alias == "user:w-test"


def test_revoked_wallet_invalidates_session(tmp_path):
    auth = WalletAuth(secret_path=tmp_path / "secret")
    _, public_b64, address = _wallet_material()
    wallet = {
        "wallet_address": address,
        "public_key_spki": public_b64,
        "display_name": "Test Wallet",
        "status": "active",
        "role": "farmer",
        "role_status": "active",
        "org_id": "farmer-org",
        "msp_id": "FarmerOrgMSP",
        "identity_alias": "user:w-test",
        "client_id_hash": "abc123",
    }
    token, _ = auth.create_session(wallet)
    wallet["status"] = "disabled"
    assert auth.parse_session(token, lambda _: wallet) is None
