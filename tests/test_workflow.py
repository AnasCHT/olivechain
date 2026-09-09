from types import SimpleNamespace

from olivechain.workflow import derive_status, transition_allowed


def ev(event_type, subject_id="BATCH-1", payload=None, event_id=None, timestamp=1):
    return SimpleNamespace(
        event_type=event_type,
        subject_id=subject_id,
        payload=payload or {},
        event_id=event_id or event_type,
        timestamp=timestamp,
    )


def test_product_status_and_next_step():
    status = derive_status("BATCH-1", [ev("cultivation"), ev("harvest")]).to_dict()
    assert status["valid"] is True
    assert status["current_step"] == "harvest"
    assert status["next_allowed"] == ["collection_transport"]
    assert transition_allowed(status, "milling")[0] is False
    assert transition_allowed(status, "collection_transport")[0] is True


def test_new_subject_requires_first_step():
    status = derive_status("BATCH-NEW", []).to_dict()
    assert transition_allowed(status, "cultivation")[0] is True
    allowed, message = transition_allowed(status, "harvest")
    assert allowed is False
    assert "First required event" in message


def test_circular_custody_must_be_accepted():
    status = derive_status("RES-1", [
        ev("residue_generation", "RES-1", {"origin_batch": "BATCH-1"}),
        ev("residue_custody", "RES-1", {"accepted": False}),
    ]).to_dict()
    assert status["next_allowed"] == ["residue_custody"]

    status = derive_status("RES-1", [
        ev("residue_generation", "RES-1", {"origin_batch": "BATCH-1"}),
        ev("residue_custody", "RES-1", {"accepted": False}),
        ev("residue_custody", "RES-1", {"accepted": True}),
    ]).to_dict()
    assert status["next_allowed"] == ["valorization"]


def test_circular_allows_multiple_outputs():
    status = derive_status("RES-1", [
        ev("residue_generation", "RES-1", {"origin_batch": "BATCH-1"}),
        ev("residue_custody", "RES-1", {"accepted": True}),
        ev("valorization", "RES-1"),
        ev("useful_output", "RES-1"),
        ev("useful_output", "RES-1"),
    ]).to_dict()
    assert status["valid"] is True
    assert status["current_step"] == "useful_output"
    assert "useful_output" in status["next_allowed"]
    assert "return_or_sale" in status["next_allowed"]
