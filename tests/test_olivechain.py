"""Tests for the OliveChain minimum viable trust chain (roadmap step 7:
security testing with actual participant roles)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from olivechain import (Registry, Ledger, EvidenceStore, IncentiveEngine,
                        build_passport, reconcile_residue, Role, EventType)
from olivechain.registry import PermissionError_
from olivechain.ledger import LedgerError
from olivechain import anomaly


@pytest.fixture
def world(tmp_path):
    reg = Registry(str(tmp_path / "registry.json"))
    led = Ledger(reg, str(tmp_path / "ledger.jsonl"))
    store = EvidenceStore(str(tmp_path / "evidence"))
    keys = {
        "farm": reg.register("farm1", "Farm One", [Role.FARMER]),
        "truck": reg.register("truck1", "Truck One", [Role.COLLECTOR]),
        "mill": reg.register("mill1", "Mill One", [Role.MILL]),
        "lab": reg.register("lab1", "Lab One", [Role.LABORATORY]),
        "proc": reg.register("proc1", "Proc One", [Role.PROCESSOR]),
        "gov": reg.register("gov1", "Authority", [Role.AUTHORITY]),
    }
    return reg, led, store, keys


def harvest(led, keys, batch="B1", qty=1000):
    return led.append(EventType.HARVEST, batch, "farm1",
                      {"date": "2025-11-01", "quantity_kg": qty,
                       "method": "hand", "location": "x"}, keys["farm"])


# ---------------- identity & permissions ----------------
def test_role_permission_enforced(world):
    _, led, _, keys = world
    with pytest.raises(PermissionError_):
        led.append(EventType.MILLING, "B1", "farm1",
                   {"received_kg": 1, "extraction_method": "x", "temperature_c": 25,
                    "oil_yield_l": 0.2, "residues_declared": []}, keys["farm"])


def test_wrong_key_rejected(world):
    _, led, _, keys = world
    with pytest.raises(LedgerError):
        led.append(EventType.HARVEST, "B1", "farm1",
                   {"date": "d", "quantity_kg": 1, "method": "m", "location": "l"},
                   keys["mill"])  # mill's key, farm's identity


def test_schema_required_fields(world):
    _, led, _, keys = world
    with pytest.raises(LedgerError):
        led.append(EventType.HARVEST, "B1", "farm1", {"date": "d"}, keys["farm"])


# ---------------- chain integrity ----------------
def test_hash_chain_and_tamper_detection(world):
    _, led, _, keys = world
    harvest(led, keys)
    harvest(led, keys, "B2")
    ok, _ = led.verify_chain()
    assert ok
    led.all()[0].payload["quantity_kg"] = 999999
    ok, problems = led.verify_chain()
    assert not ok and problems


def test_persistence_and_reload(tmp_path, world):
    reg, led, _, keys = world
    harvest(led, keys)
    led2 = Ledger(reg, led.path)
    assert len(led2) == 1
    ok, _ = led2.verify_chain()
    assert ok


# ---------------- corrections ----------------
def test_correction_supersedes_preserving_audit(world):
    _, led, _, keys = world
    h = harvest(led, keys, qty=1050)
    led.append(EventType.CORRECTION, "B1", "farm1",
               {"supersedes_event": h.event_id, "reason": "tare",
                "corrected_payload": {"quantity_kg": 1000}}, keys["farm"])
    assert h.superseded_by is not None
    assert led.effective_payload(h)["quantity_kg"] == 1000
    assert len(led) == 2  # nothing deleted
    ok, _ = led.verify_chain()
    assert ok


def test_only_author_or_authority_corrects(world):
    _, led, _, keys = world
    h = harvest(led, keys)
    with pytest.raises(PermissionError_):
        led.append(EventType.CORRECTION, "B1", "mill1",
                   {"supersedes_event": h.event_id, "reason": "x",
                    "corrected_payload": {}}, keys["mill"])
    led.append(EventType.CORRECTION, "B1", "gov1",
               {"supersedes_event": h.event_id, "reason": "audit",
                "corrected_payload": {"quantity_kg": 900}}, keys["gov"])
    assert led.effective_payload(h)["quantity_kg"] == 900


# ---------------- mass balance ----------------
def _residue_flow(led, keys, transformed=True):
    led.append(EventType.RESIDUE_GENERATION, "R1", "mill1",
               {"residue_type": "pomace", "weight_kg": 100, "moisture_pct": 60,
                "origin_batch": "B1"}, keys["mill"])
    led.append(EventType.RESIDUE_CUSTODY, "R1", "truck1",
               {"residue_id": "R1", "weight_kg": 99, "measurement_method": "scale",
                "from_org": "mill1", "to_org": "proc1", "accepted": True}, keys["truck"])
    if transformed:
        led.append(EventType.VALORIZATION, "R1", "proc1",
                   {"residue_id": "R1", "input_kg": 98, "method": "compost",
                    "outputs": [{"output_type": "compost_kg", "quantity": 60}],
                    "rejected_kg": 2}, keys["proc"])


def test_mass_balance_pass_and_fail(world):
    _, led, _, keys = world
    _residue_flow(led, keys, transformed=True)
    rec = reconcile_residue(led, "R1")
    assert rec.balanced and rec.outputs["compost_kg"] == 60

    led2 = Ledger(led.registry)
    _residue_flow(led2, keys, transformed=False)
    rec2 = reconcile_residue(led2, "R1")
    assert not rec2.balanced


def test_mass_balance_catches_inflated_transfer(world):
    _, led, _, keys = world
    led.append(EventType.RESIDUE_GENERATION, "R1", "mill1",
               {"residue_type": "pomace", "weight_kg": 100, "moisture_pct": 60,
                "origin_batch": "B1"}, keys["mill"])
    led.append(EventType.RESIDUE_CUSTODY, "R1", "truck1",
               {"residue_id": "R1", "weight_kg": 300, "measurement_method": "scale",
                "from_org": "mill1", "to_org": "proc1", "accepted": True}, keys["truck"])
    assert not reconcile_residue(led, "R1").balanced


# ---------------- anomalies ----------------
def test_implausible_yield_flagged(world):
    _, led, _, keys = world
    led.append(EventType.MILLING, "B1", "mill1",
               {"received_kg": 1000, "extraction_method": "x", "temperature_c": 25,
                "oil_yield_l": 500, "residues_declared": []}, keys["mill"])
    assert any(f.rule == "implausible_oil_yield" for f in anomaly.scan(led))


def test_duplicate_and_conflicting_custody(world):
    _, led, _, keys = world
    harvest(led, keys)
    harvest(led, keys)  # exact duplicate
    led.append(EventType.RESIDUE_GENERATION, "R1", "mill1",
               {"residue_type": "pomace", "weight_kg": 100, "moisture_pct": 60,
                "origin_batch": "B1"}, keys["mill"])
    for to in ("proc1", "proc1"):
        pass
    led.append(EventType.RESIDUE_CUSTODY, "R1", "truck1",
               {"residue_id": "R1", "weight_kg": 100, "measurement_method": "s",
                "from_org": "mill1", "to_org": "proc1", "accepted": True}, keys["truck"])
    led.append(EventType.RESIDUE_CUSTODY, "R1", "truck1",
               {"residue_id": "R1", "weight_kg": 100, "measurement_method": "s",
                "from_org": "mill1", "to_org": "farm1", "accepted": True}, keys["truck"])
    rules = {f.rule for f in anomaly.scan(led)}
    assert "duplicate_record" in rules
    assert "conflicting_custody" in rules


# ---------------- incentives ----------------
def test_rewards_gated_on_mass_balance(world):
    _, led, _, keys = world
    engine = IncentiveEngine(led, "gov1", keys["gov"])
    # accepted but never transformed -> no useful_output reward possible;
    # also directly: useful output on an unbalanced lot pays nothing
    _residue_flow(led, keys, transformed=False)
    led.append(EventType.USEFUL_OUTPUT, "R1", "proc1",
               {"residue_id": "R1", "output_type": "compost_kg",
                "quantity": 60, "unit": "kg"}, keys["proc"])
    issued = engine.run()
    assert not any(i["rule"] == "verified_recovery" for i in issued)

    # complete the loop -> now it pays, exactly once
    led.append(EventType.VALORIZATION, "R1", "proc1",
               {"residue_id": "R1", "input_kg": 98, "method": "compost",
                "outputs": [{"output_type": "compost_kg", "quantity": 60}],
                "rejected_kg": 2}, keys["proc"])
    issued = engine.run()
    assert any(i["rule"] == "verified_recovery" for i in issued)
    assert engine.run() == [] or not any(
        i["rule"] == "verified_recovery" for i in engine.run())


def test_flagged_events_not_rewarded_until_resolved(world):
    _, led, _, keys = world
    engine = IncentiveEngine(led, "gov1", keys["gov"])
    m = led.append(EventType.MILLING, "B1", "mill1",
                   {"received_kg": 1000, "extraction_method": "x", "temperature_c": 25,
                    "oil_yield_l": 500, "residues_declared": []}, keys["mill"])
    fl = engine.flag(m.event_id, "implausible_oil_yield", "48% yield")
    assert engine.run() == []  # review first, no reward
    engine.resolve(fl.event_id, "cleared", "measurement re-verified on site")
    issued = engine.run()
    assert any(i["rule"] == "prompt_records" for i in issued)


def test_reward_events_are_signed_ledger_records(world):
    _, led, _, keys = world
    engine = IncentiveEngine(led, "gov1", keys["gov"])
    harvest(led, keys)
    led.append(EventType.LAB_VERIFICATION, "B1", "lab1",
               {"quality_class": "extra_virgin", "results": {}}, keys["lab"])
    engine.run()
    ok, _ = led.verify_chain()
    assert ok
    assert engine.balances().get("lab1") == 15


# ---------------- evidence & passport ----------------
def test_evidence_substitution_detected(world, tmp_path):
    _, _, store, _ = world
    ref = store.put("doc.pdf", b"original")
    assert store.verify(ref)
    with open(ref["uri"], "wb") as f:
        f.write(b"swapped")
    assert not store.verify(ref)


def test_passport_assembly(world):
    _, led, store, keys = world
    harvest(led, keys)
    led.append(EventType.MILLING, "B1", "mill1",
               {"received_kg": 1000, "extraction_method": "x", "temperature_c": 25,
                "oil_yield_l": 180,
                "residues_declared": [{"residue_id": "R1", "residue_type": "pomace",
                                       "weight_kg": 500}]}, keys["mill"])
    _residue_flow(led, keys)
    p = build_passport(led, "B1", store)
    assert p["ledger_verified"]
    assert len(p["stages"]) == 2
    assert p["circular"][0]["mass_balance_ok"]
