"""Verifiable Credential crypto: JCS proof round-trip, tamper and forged-key
detection, did:key and base58 correctness."""
import copy
import os

from olivechain import credentials as C
from olivechain.crypto import KeyPair

PASSPORT = {
    "batch_id": "BATCH-1", "ledger_verified": True, "consumer_scans": 3,
    "stages": [{"stage": "Milled", "by": "Fes Mill", "timestamp": 1785000000.0}],
    "circular": [{"residue_id": "RES-1", "recovery_pct": 97.41, "mass_balance_ok": True}],
    "rewards": [{"recipient": "mill", "for": "prompt_records", "amount": 5}],
}


def _vc(signer):
    return C.build_passport_credential(
        PASSPORT, signer=signer, head_hash="ab" * 32, height=10,
        content_sha256="cd" * 32, credential_id="urn:uuid:x",
        subject_id="https://x/01/09506000134352/10/BATCH-1")


def test_credential_roundtrip_and_shape():
    signer = KeyPair.generate()
    vc = _vc(signer)
    assert vc["type"] == ["VerifiableCredential", "OliveOilPassportCredential"]
    assert vc["@context"][0] == "https://www.w3.org/ns/credentials/v2"
    assert vc["proof"]["cryptosuite"] == "eddsa-jcs-2022"
    assert vc["issuer"].startswith("did:key:z6Mk")
    assert C.verify_passport_credential(vc)["verified"] is True


def test_credential_tamper_detected():
    signer = KeyPair.generate()
    vc = _vc(signer)
    bad = copy.deepcopy(vc)
    bad["credentialSubject"]["ledgerVerified"] = False
    assert C.verify_passport_credential(bad)["verified"] is False


def test_credential_forged_key_detected():
    signer, other = KeyPair.generate(), KeyPair.generate()
    vc = _vc(signer)
    bad = copy.deepcopy(vc)
    bad["proof"]["verificationMethod"] = C.did_key_ed25519(other.public_hex) + "#x"
    assert C.verify_passport_credential(bad)["verified"] is False


def test_did_key_and_base58_roundtrip():
    kp = KeyPair.generate()
    did = C.did_key_ed25519(kp.public_hex)
    assert did.startswith("did:key:z6Mk")
    assert C._public_hex_from_did_key(did) == kp.public_hex
    blob = os.urandom(32)
    assert C.b58decode(C.b58encode(blob)) == blob


def test_gs1_digital_link():
    assert (C.gs1_digital_link("https://oil.example/", "09506000134352", "BATCH-1")
            == "https://oil.example/01/09506000134352/10/BATCH-1")
