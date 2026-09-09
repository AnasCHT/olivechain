import json

from olivechain.crypto import KeyPair
from olivechain.fabric_ledger import FabricLedger
from olivechain.models import EventType, Role
from olivechain.registry import Organization


class FakeRegistry:
    def __init__(self):
        self.org = Organization(
            org_id="farm-app",
            name="Farm App",
            roles=[Role.FARMER],
            public_key=KeyPair.generate().public_hex,
        )

    def get(self, org_id):
        assert org_id == "farm-app"
        return self.org


class FakeRouter:
    def __init__(self):
        self.calls = []
        self.rows = []

    def evaluate(self, transaction, args=(), role="farmer"):
        self.calls.append(("evaluate", role, transaction, list(args)))
        if transaction == "GetAllEvents":
            return self.rows
        if transaction == "GetEventsForSubject":
            return [row for row in self.rows if row["subject_id"] == args[0]]
        if transaction == "GetEventsByType":
            return [row for row in self.rows if row["event_type"] == args[0]]
        if transaction in {"GetEvent", "GetEffectiveEvent"}:
            return next(row for row in self.rows if row["event_id"] == args[0])
        return []

    def submit(self, role, transaction, args=()):
        self.calls.append(("submit", role, transaction, list(args)))
        payload = json.loads(args[3])
        row = {
            "docType": "event",
            "event_id": args[0],
            "event_type": args[1],
            "subject_id": args[2],
            "actor_org": "farmer-org",
            "actor_msp": "FarmerOrgMSP",
            "actor_role": role,
            "client_id_hash": "abc",
            "timestamp": 1.0,
            "timestamp_rfc3339": "2026-08-01T00:00:01Z",
            "payload": payload,
            "evidence": json.loads(args[4]),
            "fabric_tx_id": "tx1",
            "event_hash": "hash1",
            "signed_by_fabric": True,
            "superseded_by": "",
        }
        self.rows.append(row)
        return row


def test_commit_routes_by_existing_role_and_preserves_app_actor():
    router = FakeRouter()
    ledger = FabricLedger(FakeRegistry(), router, cache_seconds=0)
    key = KeyPair.generate()

    event = ledger.append(
        EventType.CULTIVATION,
        "BATCH-1",
        "farm-app",
        {"farm_id": "F1", "plot_id": "P1", "cultivar": "Picholine", "practices": {}},
        key,
    )

    submit = next(call for call in router.calls if call[0] == "submit")
    assert submit[1] == "farmer"
    assert submit[2] == "SubmitEvent"
    assert event.actor_org == "farm-app"
    assert event.payload["farm_id"] == "F1"
    assert "_olivechain_app" not in event.payload


def test_verify_fabric_event_view():
    router = FakeRouter()
    ledger = FabricLedger(FakeRegistry(), router, cache_seconds=0)
    key = KeyPair.generate()
    ledger.append(
        EventType.CULTIVATION,
        "BATCH-1",
        "farm-app",
        {"farm_id": "F1", "plot_id": "P1", "cultivar": "Picholine", "practices": {}},
        key,
    )
    ok, problems = ledger.verify_chain()
    assert ok
    assert problems == []
