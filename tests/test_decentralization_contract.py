"""Compatibility guard for the Fabric decentralization migration.

The backend is allowed to change, but the established product surfaces must not
silently disappear while the local ledger is replaced by a Fabric adapter.
"""
from fastapi.testclient import TestClient

from olivechain import EvidenceStore, Ledger, Registry
from olivechain.api import create_app
from olivechain.crypto import KeyPair


def test_required_product_routes_remain_registered(tmp_path):
    registry = Registry(str(tmp_path / "registry.json"))
    ledger = Ledger(registry, str(tmp_path / "ledger.jsonl"))
    evidence = EvidenceStore(str(tmp_path / "evidence"))
    app = create_app(registry, ledger, evidence, passport_signer=KeyPair.generate())

    routes = {(method, route.path) for route in app.routes for method in route.methods}
    required = {
        ("GET", "/"),
        ("GET", "/portal"),
        ("GET", "/verify"),
        ("GET", "/m"),
        ("POST", "/events/prepare"),
        ("POST", "/events/commit"),
        ("GET", "/events"),
        ("POST", "/evidence"),
        ("GET", "/audit"),
        ("GET", "/governance"),
        ("GET", "/rewards/due"),
        ("GET", "/rewards/balances"),
        ("GET", "/passport-view/{batch_id}"),
        ("GET", "/passport/{batch_id}.pdf"),
        ("GET", "/passport/{batch_id}/credential"),
        ("GET", "/labels/{batch_id}"),
        ("GET", "/qr/{batch_id}.svg"),
        ("GET", "/residues/{residue_id}/balance"),
    }
    assert required <= routes


def test_home_page_still_serves_the_trust_dashboard(tmp_path):
    registry = Registry(str(tmp_path / "registry.json"))
    ledger = Ledger(registry, str(tmp_path / "ledger.jsonl"))
    evidence = EvidenceStore(str(tmp_path / "evidence"))
    client = TestClient(create_app(registry, ledger, evidence, passport_signer=KeyPair.generate()))

    response = client.get("/")
    assert response.status_code == 200
    assert "OliveChain — Trust Dashboard" in response.text
    assert "Batch passports" in response.text
    assert "Circular recovery" in response.text
    assert "EcoPoints leaderboard" in response.text
    assert "Ledger explorer" in response.text
    assert "Live audit" in response.text
