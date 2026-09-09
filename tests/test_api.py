"""API-layer tests: onboarding, the two-phase signed flow, hardening gates,
consumer scans, and the governance worklist — all through the HTTP surface."""
import uuid

import pytest
from fastapi.testclient import TestClient

from olivechain import EvidenceStore, Ledger, Registry
from olivechain import api as api_module
from olivechain.api import create_app
from olivechain.crypto import KeyPair, canonical_json
from olivechain.models import Role


@pytest.fixture
def env(tmp_path):
    registry = Registry(str(tmp_path / "registry.json"))
    ledger = Ledger(registry, str(tmp_path / "ledger.jsonl"))
    store = EvidenceStore(str(tmp_path / "evidence"))
    portal_kp = registry.register("consumer-portal", "Portal", [Role.CONSUMER])
    app = create_app(registry, ledger, store,
                     consumer_signer=("consumer-portal", portal_kp),
                     passport_signer=KeyPair.generate())
    return TestClient(app), registry, ledger


def register(client, org_id, roles, **extra):
    r = client.post("/organizations/register",
                    json={"org_id": org_id, "name": org_id, "roles": roles, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def submit(client, key_hex, org, etype, subject, payload, evidence=None):
    prep = client.post("/events/prepare", json={
        "event_type": etype, "subject_id": subject, "actor_org": org,
        "payload": payload, "evidence": evidence or []})
    assert prep.status_code == 200, prep.text
    body = prep.json()["body"]
    sig = KeyPair.from_private_hex(key_hex).sign(canonical_json(body))
    return client.post("/events/commit", json={"body": body, "signature": sig})


HARVEST = {"date": "2026-07-26", "quantity_kg": 100, "method": "hand", "location": "x"}


# --------------------------------------------------------------- onboarding
def test_register_returns_key_once(env):
    client, registry, _ = env
    res = register(client, "farm-a", ["farmer"])
    assert len(res["private_key"]) == 64
    assert registry.get("farm-a").public_key == res["public_key"]
    # the registry never stores the private key
    assert "private" not in open(registry.path).read()


def test_register_rejects_bad_input(env):
    client, _, _ = env
    assert client.post("/organizations/register", json={
        "org_id": "BAD ID", "name": "x", "roles": ["farmer"]}).status_code == 400
    assert client.post("/organizations/register", json={
        "org_id": "ok-id", "name": "x", "roles": ["wizard"]}).status_code == 400
    register(client, "dup-org", ["farmer"])
    assert client.post("/organizations/register", json={
        "org_id": "dup-org", "name": "x", "roles": ["farmer"]}).status_code == 409


def test_onboard_code_gate(env, monkeypatch):
    client, _, _ = env
    monkeypatch.setattr(api_module, "ONBOARD_CODE", "sesame")
    assert client.post("/organizations/register", json={
        "org_id": "gated", "name": "x", "roles": ["farmer"]}).status_code == 403
    register(client, "gated", ["farmer"], onboard_code="sesame")


# --------------------------------------------------------- two-phase signing
def test_signed_flow_end_to_end(env):
    client, _, ledger = env
    farm = register(client, "farm-b", ["farmer"])
    r = submit(client, farm["private_key"], "farm-b", "harvest", "BATCH-1", HARVEST)
    assert r.status_code == 200, r.text
    assert len(ledger) == 1
    ok, problems = ledger.verify_chain()
    assert ok, problems


def test_commit_rechecks_role(env):
    client, _, _ = env
    farm = register(client, "farm-c", ["farmer"])
    # craft a milling body directly — prepare would refuse, commit must too
    head = client.get("/head").json()["head_hash"]
    body = {"event_id": str(uuid.uuid4()), "event_type": "milling",
            "subject_id": "B", "actor_org": "farm-c", "timestamp": 1.0,
            "payload": {"received_kg": 1, "extraction_method": "x", "temperature_c": 1,
                        "oil_yield_l": 1, "residues_declared": []},
            "evidence": [], "prev_hash": head}
    sig = KeyPair.from_private_hex(farm["private_key"]).sign(canonical_json(body))
    assert client.post("/events/commit", json={"body": body, "signature": sig}).status_code == 403


def test_commit_rejects_malformed_bodies(env):
    client, _, _ = env
    farm = register(client, "farm-d", ["farmer"])
    kp = KeyPair.from_private_hex(farm["private_key"])
    head = client.get("/head").json()["head_hash"]
    base = {"event_id": str(uuid.uuid4()), "event_type": "harvest", "subject_id": "B",
            "actor_org": "farm-d", "timestamp": 1.0, "payload": dict(HARVEST),
            "evidence": [], "prev_hash": head}
    extra = dict(base, superseded_by="evil")
    r = client.post("/events/commit",
                    json={"body": extra, "signature": kp.sign(canonical_json(extra))})
    assert r.status_code == 422
    missing = dict(base, payload={"date": "d"})
    r = client.post("/events/commit",
                    json={"body": missing, "signature": kp.sign(canonical_json(missing))})
    assert r.status_code == 422
    bad_sig = client.post("/events/commit", json={"body": base, "signature": "ab" * 64})
    assert bad_sig.status_code == 401


def test_commit_rejects_duplicate_event_id(env):
    client, _, _ = env
    farm = register(client, "farm-e", ["farmer"])
    kp = KeyPair.from_private_hex(farm["private_key"])
    prep = client.post("/events/prepare", json={
        "event_type": "harvest", "subject_id": "B", "actor_org": "farm-e",
        "payload": HARVEST, "evidence": []}).json()["body"]
    sig = kp.sign(canonical_json(prep))
    assert client.post("/events/commit", json={"body": prep, "signature": sig}).status_code == 200
    replay = dict(prep, prev_hash=client.get("/head").json()["head_hash"])
    sig2 = kp.sign(canonical_json(replay))
    assert client.post("/events/commit", json={"body": replay, "signature": sig2}).status_code == 409


# ------------------------------------------------------------------ evidence
def test_evidence_upload_sanitizes_name(env):
    client, _, _ = env
    r = client.post("/evidence", json={"name": "../../evil.txt", "content_base64": "aGk="})
    assert r.status_code == 200
    ref = r.json()
    assert ".." not in ref["uri"] and ref["name"] == "evil.txt"
    assert client.post("/evidence", json={"name": "x.txt", "content_base64": "!!"}).status_code == 400


# -------------------------------------------------------------------- scans
def test_scan_records_signed_event(env):
    client, _, ledger = env
    farm = register(client, "farm-f", ["farmer"])
    submit(client, farm["private_key"], "farm-f", "harvest", "BATCH-S", HARVEST)
    assert client.post("/scan/NOPE").status_code == 404
    r = client.post("/scan/BATCH-S")
    assert r.status_code == 200 and r.json()["consumer_scans"] == 1
    ok, problems = ledger.verify_chain()
    assert ok, problems


# --------------------------------------------------------------- governance
def test_governance_flag_blocks_reward_until_resolved(env):
    client, _, _ = env
    mill = register(client, "mill-g", ["mill"])
    gov = register(client, "gov-g", ["authority"])
    sus = submit(client, mill["private_key"], "mill-g", "milling", "BATCH-G", {
        "received_kg": 1000, "extraction_method": "x", "temperature_c": 20,
        "oil_yield_l": 500, "residues_declared": []}).json()

    g = client.get("/governance").json()
    anom = next(a for a in g["unflagged_anomalies"] if a["subject_event"] == sus["event_id"])
    assert any(sus["event_id"] in d["basis_events"] for d in g["due_rewards"])

    submit(client, gov["private_key"], "gov-g", "review_flag", sus["event_id"], {
        "subject_event": sus["event_id"], "rule": anom["rule"], "detail": anom["detail"]})
    g2 = client.get("/governance").json()
    assert not any(sus["event_id"] in d["basis_events"] for d in g2["due_rewards"])
    flag = next(f for f in g2["open_flags"] if f["subject_event"] == sus["event_id"])

    submit(client, gov["private_key"], "gov-g", "review_resolution", flag["flag_event"], {
        "flag_event": flag["flag_event"], "decision": "cleared", "rationale": "verified on site"})
    g3 = client.get("/governance").json()
    assert not any(f["flag_event"] == flag["flag_event"] for f in g3["open_flags"])

    # authority issues what is due; balances reflect it
    for d in client.get("/rewards/due").json():
        r = submit(client, gov["private_key"], "gov-g", "reward_issued", d["recipient"], {
            "recipient": d["recipient"], "amount": d["amount"],
            "reward_rule": d["reward_rule"], "basis_events": d["basis_events"],
            "transferable": False})
        assert r.status_code == 200, r.text
    assert client.get("/rewards/due").json() == []
    balances = {b["org_id"]: b["points"] for b in client.get("/rewards/balances").json()}
    assert balances.get("mill-g") == 5
    assert client.get("/audit").json()["chain_valid"]


# ----------------------------------------------------------------- QR labels
def test_qr_svg_for_known_batch_only(env):
    client, _, _ = env
    farm = register(client, "farm-q", ["farmer"])
    submit(client, farm["private_key"], "farm-q", "harvest", "BATCH-Q", HARVEST)
    r = client.get("/qr/BATCH-Q.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in r.content
    assert client.get("/qr/NOPE.svg").status_code == 404


# --------------------------------------------------------- signed PDF passport
def test_signed_pdf_and_attestation(tmp_path):
    registry = Registry(str(tmp_path / "registry.json"))
    ledger = Ledger(registry, str(tmp_path / "ledger.jsonl"))
    store = EvidenceStore(str(tmp_path / "evidence"))
    signer = KeyPair.generate()
    client = TestClient(create_app(registry, ledger, store, passport_signer=signer))

    farm = register(client, "farm-pdf", ["farmer"])
    submit(client, farm["private_key"], "farm-pdf", "harvest", "BATCH-PDF", HARVEST)

    # PDF renders
    r = client.get("/passport/BATCH-PDF.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-" and len(r.content) > 2000
    assert "BATCH-PDF" in r.headers["content-disposition"]
    assert client.get("/passport/NOPE.pdf").status_code == 404

    # issuer key published
    issuer = client.get("/passport/issuer").json()
    assert issuer["public_key"] == signer.public_hex

    # build the attestation exactly as the endpoint does, verify it round-trips
    from olivechain.passport import build_passport
    from olivechain.passport_pdf import build_passport_pdf
    passport = build_passport(ledger, "BATCH-PDF", store)
    evs = ledger.all()
    _, att = build_passport_pdf(passport, signer=signer, issuer_pub=signer.public_hex,
                                head_hash=evs[-1].event_hash, height=len(evs),
                                verify_url="http://x/m?batch=BATCH-PDF")
    res = client.post("/passport/verify", json=att).json()
    assert res["signature_valid"] is True
    assert res["matches_live_passport"] is True

    # tampering breaks the signature
    bad = dict(att, content_sha256="0" * 64)
    assert client.post("/passport/verify", json=bad).json()["signature_valid"] is False


# --------------------------------------------------------- operator auth gate
def test_operator_auth_gate(env, monkeypatch):
    client, _, _ = env
    monkeypatch.setattr(api_module, "ADMIN_USER", "op")
    monkeypatch.setattr(api_module, "ADMIN_PASS", "s3cret")

    # operator surfaces require credentials
    assert client.get("/organizations").status_code == 401
    assert client.get("/").status_code == 401
    assert client.get("/events").status_code == 401
    ok = client.get("/organizations", auth=("op", "s3cret"))
    assert ok.status_code == 200
    assert client.get("/organizations", auth=("op", "wrong")).status_code == 401

    # consumer surfaces stay open
    for path in ("/health", "/stats", "/subjects", "/m", "/verify", "/i18n.js"):
        assert client.get(path).status_code == 200, path


def test_admin_export(env, monkeypatch):
    client, _, _ = env
    farm = register(client, "farm-x", ["farmer"])
    submit(client, farm["private_key"], "farm-x", "harvest", "BATCH-X", HARVEST)

    # refuses when no credentials are configured
    assert client.get("/admin/export").status_code == 503

    monkeypatch.setattr(api_module, "ADMIN_USER", "op")
    monkeypatch.setattr(api_module, "ADMIN_PASS", "pw")
    assert client.get("/admin/export").status_code == 401
    r = client.get("/admin/export", auth=("op", "pw"))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/gzip"
    # it is a real backup archive containing the ledger
    from olivechain.backup import read_manifest
    manifest = read_manifest(r.content)
    assert manifest["height"] == 1
    assert "data/ledger.jsonl" in manifest["files"]


# ---------------------------------------------------- verifiable credential
def test_verifiable_credential_endpoints(env):
    client, _, _ = env
    farm = register(client, "farm-vc", ["farmer"])
    submit(client, farm["private_key"], "farm-vc", "harvest", "BATCH-VC", HARVEST)

    r = client.get("/passport/BATCH-VC/credential")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/ld+json")
    vc = r.json()
    assert "VerifiableCredential" in vc["type"]
    assert vc["proof"]["cryptosuite"] == "eddsa-jcs-2022"
    assert vc["credentialSubject"]["batchId"] == "BATCH-VC"
    assert "/01/" in vc["credentialSubject"]["id"]  # GS1 Digital Link subject

    res = client.post("/credentials/verify", json=vc).json()
    assert res["verified"] is True and res["issuer_recognized"] is True

    vc["credentialSubject"]["ledgerVerified"] = False
    assert client.post("/credentials/verify", json=vc).json()["verified"] is False


def test_gs1_resolver_redirects(env):
    client, _, _ = env
    r = client.get("/01/09506000134352/10/BATCH-Z", follow_redirects=False)
    assert r.status_code in (307, 308)
    assert "batch=BATCH-Z" in r.headers["location"]


# ------------------------------------------------------------------- reads
def test_read_endpoints(env):
    client, _, _ = env
    farm = register(client, "farm-h", ["farmer"])
    submit(client, farm["private_key"], "farm-h", "harvest", "BATCH-R", HARVEST)
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/health?deep=true").json()["chain_valid"] is True
    assert client.get("/stats").json()["height"] == 1
    assert client.get("/subjects").json()["batches"] == ["BATCH-R"]
    evs = client.get("/events?event_type=harvest").json()
    assert evs["total"] == 1 and evs["events"][0]["actor_name"] == "farm-h"
    schema = client.get("/schema").json()
    assert any(s["event_type"] == "milling" for s in schema)
    r = client.get("/")
    assert r.status_code == 200
    assert "Content-Security-Policy" in r.headers
