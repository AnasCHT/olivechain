"""W3C Verifiable Credentials for the batch passport.

Expresses a passport as a W3C VC 2.0 credential signed with a Data Integrity
proof (`eddsa-jcs-2022`): the issuer is a `did:key` derived from the passport
issuer's Ed25519 key, and the proof is an Ed25519 signature over the
JCS-canonicalized (RFC 8785) credential. Verification is self-contained — the
public key travels in the `did:key` verification method — so any holder can
check the credential offline, while /credentials/verify additionally confirms
the issuer is the one this server recognizes.

Also builds GS1 Digital Link URIs so the QR/label layer can speak the standard
supply-chain identifier syntax (GTIN + lot). Real GTINs must be assigned by
GS1; the GTIN is configurable and defaults to a documented placeholder.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .crypto import verify_signature

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
# multicodec varint prefix for an Ed25519 public key
_ED25519_MULTICODEC = b"\xed\x01"


def b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    out = ""
    while n > 0:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    pad = len(b) - len(b.lstrip(b"\x00"))
    return "1" * pad + out


def b58decode(s: str) -> bytes:
    n = 0
    for ch in s:
        n = n * 58 + _B58.index(ch)
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + body


def jcs(obj) -> bytes:
    """RFC 8785 JSON Canonicalization Scheme, for the value types used here
    (objects with ASCII keys, strings, ints, bools, null, arrays). Numbers are
    kept as ints/strings in credentials, sidestepping float serialization."""
    import json
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def did_key_ed25519(public_hex: str) -> str:
    raw = bytes.fromhex(public_hex)
    return "did:key:z" + b58encode(_ED25519_MULTICODEC + raw)


def _public_hex_from_did_key(did: str) -> str:
    frag = did.split("#", 1)[0]
    if not frag.startswith("did:key:z"):
        raise ValueError("unsupported verification method")
    decoded = b58decode(frag[len("did:key:z"):])
    if not decoded.startswith(_ED25519_MULTICODEC):
        raise ValueError("not an Ed25519 did:key")
    return decoded[len(_ED25519_MULTICODEC):].hex()


def _iso(ts: float | None = None) -> str:
    dt = datetime.fromtimestamp(ts, timezone.utc) if ts else datetime.now(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash_data(credential: dict, proof_options: dict) -> bytes:
    return (hashlib.sha256(jcs(proof_options)).digest()
            + hashlib.sha256(jcs(credential)).digest())


def build_passport_credential(passport: dict, *, signer, head_hash: str, height: int,
                              content_sha256: str, credential_id: str,
                              subject_id: str) -> dict:
    """Build and sign a W3C VC for the passport. `signer` is the issuer KeyPair."""
    issuer_did = did_key_ed25519(signer.public_hex)
    vm = issuer_did + "#" + issuer_did.split(":", 2)[2]

    subject = {
        "id": subject_id,
        "type": "OliveOilBatch",
        "batchId": passport["batch_id"],
        "ledgerVerified": bool(passport["ledger_verified"]),
        "ledgerHeight": int(height),
        "ledgerHeadHash": head_hash,
        "consumerScans": int(passport.get("consumer_scans", 0)),
        "passportContentSha256": content_sha256,
        "stages": [{"stage": s["stage"], "by": s["by"],
                    "date": _iso(s["timestamp"])[:10]} for s in passport.get("stages", [])],
        "recovery": [{"residueId": c.get("residue_id"),
                      "recoveryPct": str(c.get("recovery_pct")),
                      "massBalanceOk": bool(c.get("mass_balance_ok"))}
                     for c in passport.get("circular", [])],
        "rewards": [{"recipient": r["recipient"], "rule": r["for"],
                     "points": int(r["amount"])} for r in passport.get("rewards", [])],
    }
    credential = {
        "@context": ["https://www.w3.org/ns/credentials/v2"],
        "id": credential_id,
        "type": ["VerifiableCredential", "OliveOilPassportCredential"],
        "issuer": issuer_did,
        "validFrom": _iso(),
        "credentialSubject": subject,
    }
    proof_options = {
        "@context": credential["@context"],
        "type": "DataIntegrityProof",
        "cryptosuite": "eddsa-jcs-2022",
        "created": _iso(),
        "verificationMethod": vm,
        "proofPurpose": "assertionMethod",
    }
    sig_hex = signer.sign(_hash_data(credential, proof_options))
    proof = {k: v for k, v in proof_options.items() if k != "@context"}
    proof["proofValue"] = "z" + b58encode(bytes.fromhex(sig_hex))
    credential["proof"] = proof
    return credential


def verify_passport_credential(vc: dict) -> dict:
    """Verify a credential's Data Integrity proof. Self-contained: the key is
    taken from the proof's did:key verification method."""
    try:
        proof = dict(vc["proof"])
        proof_value = proof.pop("proofValue")
        if not proof_value.startswith("z"):
            return {"verified": False, "error": "unsupported multibase"}
        sig_hex = b58decode(proof_value[1:]).hex()
        credential = {k: v for k, v in vc.items() if k != "proof"}
        proof_options = {"@context": vc.get("@context"), **proof}
        pub_hex = _public_hex_from_did_key(proof["verificationMethod"])
        ok = verify_signature(pub_hex, _hash_data(credential, proof_options), sig_hex)
        return {"verified": bool(ok), "issuer": vc.get("issuer"),
                "verification_method": proof["verificationMethod"]}
    except (KeyError, ValueError, TypeError) as e:
        return {"verified": False, "error": str(e)}


def gs1_digital_link(base_url: str, gtin: str, batch: str) -> str:
    from urllib.parse import quote
    return f"{base_url.rstrip('/')}/01/{gtin}/10/{quote(batch, safe='')}"
