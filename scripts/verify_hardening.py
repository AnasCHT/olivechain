"""Security hardening verification: attacks must fail, legit flows must pass.
Run against a live server: python scripts/verify_hardening.py"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from olivechain.crypto import KeyPair, canonical_json

BASE = "http://localhost:8000"
FARM = "test-e2e-farm"
FARM_KEY = "577c03f1b3d741d5d518c9898c9448f2151475fbf50ad2ef6b3824162ba14636"
kp = KeyPair.from_private_hex(FARM_KEY)


def call(path, obj=None, method=None):
    data = json.dumps(obj).encode() if obj is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read()), dict(r.headers)


def expect(code, path, obj=None, method=None):
    try:
        call(path, obj, method)
        raise AssertionError(f"{path} unexpectedly succeeded (wanted {code})")
    except urllib.error.HTTPError as e:
        assert e.code == code, f"{path}: wanted {code}, got {e.code}: {e.read()[:120]}"


head, _ = call("/head")


def make_body(event_type, payload, prev_hash=None):
    return {"event_id": str(uuid.uuid4()), "event_type": event_type,
            "subject_id": "BATCH-SEC-001", "actor_org": FARM,
            "timestamp": time.time(), "payload": payload, "evidence": [],
            "prev_hash": prev_hash or head["head_hash"]}


def sign(body):
    return kp.sign(canonical_json(body))


# 1. Role bypass: farmer signs a MILLING body directly (skipping prepare) -> 403
body = make_body("milling", {"received_kg": 1, "extraction_method": "x",
                             "temperature_c": 1, "oil_yield_l": 1, "residues_declared": []})
expect(403, "/events/commit", {"body": body, "signature": sign(body)})
print("role bypass at commit: blocked (403)")

# 2. Extra body keys -> 422
body = make_body("harvest", {"date": "d", "quantity_kg": 1, "method": "m", "location": "l"})
body["superseded_by"] = "evil"
expect(422, "/events/commit", {"body": body, "signature": sign(body)})
print("extra body keys: blocked (422)")

# 3. Missing required fields, signed directly -> 422
body = make_body("harvest", {"date": "only"})
expect(422, "/events/commit", {"body": body, "signature": sign(body)})
print("missing fields at commit: blocked (422)")

# 4. Legit signed harvest still works
body = make_body("harvest", {"date": "2026-07-26", "quantity_kg": 7, "method": "hand", "location": "x"})
commit, headers = call("/events/commit", {"body": body, "signature": sign(body)})
print("legit signed commit: ok", commit["event_hash"][:12])

# 5. Reused event_id -> 409
dup = dict(body, prev_hash=commit["event_hash"], timestamp=time.time())
expect(409, "/events/commit", {"body": dup, "signature": sign(dup)})
print("reused event_id: blocked (409)")

# 6. Oversize payload -> 413 at prepare
expect(413, "/events/prepare", {"event_type": "harvest", "subject_id": "B",
    "actor_org": FARM, "payload": {"date": "d", "quantity_kg": 1, "method": "m",
                                   "location": "x" * 40000}, "evidence": []})
print("oversize payload: blocked (413)")

# 7. Evidence path traversal name is sanitized
ref, _ = call("/evidence", {"name": "../../evil.txt", "content_base64": "aGk="})
assert "evil.txt" in ref["name"] and ".." not in ref["uri"], ref
print("evidence name sanitized:", ref["name"])

# 8. Bad org_id at register -> 400
expect(400, "/organizations/register", {"org_id": "BAD ID!!", "name": "x", "roles": ["farmer"]})
print("bad org_id: blocked (400)")

# 9. Scan rate limit: 10/min allowed, 11th -> 429
codes = []
for i in range(11):
    try:
        call("/scan/BATCH-2025-001", method="POST", obj=None)
        codes.append(200)
    except urllib.error.HTTPError as e:
        codes.append(e.code)
assert codes[-1] == 429 and codes[0] == 200, codes
print("scan rate limit: 11th call blocked (429)")

# 10. Security headers present
_, h = call("/head")
hl = {k.lower() for k in h}
for k in ("x-content-type-options", "x-frame-options", "content-security-policy", "referrer-policy"):
    assert k in hl, f"missing header {k}"
print("security headers: present")

# 11. Chain still valid
audit, _ = call("/audit")
assert audit["chain_valid"], audit["problems"]
print("chain valid after hardening tests")
