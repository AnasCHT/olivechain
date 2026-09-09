"""Verify the signed PDF passport: content is present, the attestation
signature checks out, and tampering is detected. Run against a live server."""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from pypdf import PdfReader

from olivechain import EvidenceStore, Ledger, Registry
from olivechain.crypto import KeyPair
from olivechain.passport import build_passport
from olivechain.passport_pdf import build_passport_pdf

BASE = "http://localhost:8000"
BATCH = "BATCH-2025-001"


def post(path, obj):
    req = urllib.request.Request(BASE + path, data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


# rebuild the same objects the server uses (read-only)
registry = Registry("data/registry.json")
ledger = Ledger(registry, "data/ledger.jsonl")
store = EvidenceStore("evidence_store")
signer = KeyPair.from_private_hex(open("data/passport_issuer.key").read().strip())

passport = build_passport(ledger, BATCH, store)
evs = ledger.all()
pdf_bytes, att = build_passport_pdf(
    passport, signer=signer, issuer_pub=signer.public_hex,
    head_hash=evs[-1].event_hash, height=len(evs),
    verify_url=f"{BASE}/m?batch={BATCH}", lang="en")

# 1. content present in the rendered PDF
import io
text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf_bytes)).pages)
for needle in ("OliveChain", BATCH, "Milled", "recovered", "How to verify"):
    assert needle in text, f"missing from PDF text: {needle!r}"
print("PDF content OK (batch, stages, recovery, verification block present)")

# 2. signature verifies via the server's /passport/verify
res = post("/passport/verify", att)
assert res["signature_valid"] is True, res
assert res["matches_live_passport"] is True, res
print("attestation signature valid; snapshot matches live passport")

# 3. tamper the content hash -> signature must fail
bad = dict(att, content_sha256="0" * 64)
res2 = post("/passport/verify", bad)
assert res2["signature_valid"] is False, res2
print("tampered attestation rejected (signature_valid=false)")

# 4. issuer key endpoint matches our signer
issuer = json.loads(urllib.request.urlopen(BASE + "/passport/issuer").read())
assert issuer["public_key"] == signer.public_hex
print("published issuer key matches signer")

print("\nAll signed-PDF checks passed.")
