"""Ordered OliveChain product and circular workflow helpers.

Fabric chaincode is authoritative for write enforcement. This module mirrors
its status model for the FastAPI UI and for the optional local backend.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

PRODUCT_STEPS = [
    "cultivation",
    "harvest",
    "collection_transport",
    "milling",
    "lab_verification",
    "bottling",
    "distribution_retail",
]

CIRCULAR_STEPS = [
    "residue_generation",
    "residue_custody",
    "valorization",
    "useful_output",
    "return_or_sale",
    "env_accounting",
]

PRODUCT_LABELS = {
    "cultivation": "Farming recorded",
    "harvest": "Harvest recorded",
    "collection_transport": "Olives transported",
    "milling": "Olives milled",
    "lab_verification": "Quality verified",
    "bottling": "Oil bottled",
    "distribution_retail": "Delivered to seller",
}

CIRCULAR_LABELS = {
    "residue_generation": "Residue generated",
    "residue_custody": "Residue in custody transfer",
    "valorization": "Residue valorized",
    "useful_output": "Useful output recorded",
    "return_or_sale": "Output returned or sold",
    "env_accounting": "Environmental accounting complete",
}


@dataclass
class WorkflowStatus:
    subject_id: str
    workflow: str = "unknown"
    exists: bool = False
    current_step: str = "not_started"
    current_label: str = "Not started"
    current_step_number: int = 0
    total_steps: int = 0
    progress_pct: float = 0.0
    next_allowed: list[str] | None = None
    complete: bool = False
    valid: bool = True
    message: str = "No workflow event has been recorded for this subject."
    last_event_id: str = ""
    updated_at: str = ""
    origin_batch: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["next_allowed"] = list(self.next_allowed or [])
        return data


def _event_type(event) -> str:
    return getattr(event, "event_type", "")


def _event_payload(event) -> dict:
    value = getattr(event, "payload", {})
    return value if isinstance(value, dict) else {}


def _event_timestamp(event) -> str:
    timestamp = getattr(event, "timestamp", 0)
    return str(timestamp or "")


def _workflow_for_type(event_type: str):
    if event_type in PRODUCT_STEPS:
        return "product", PRODUCT_STEPS
    if event_type in CIRCULAR_STEPS:
        return "circular", CIRCULAR_STEPS
    return None, None


def derive_status(subject_id: str, events: Iterable) -> WorkflowStatus:
    relevant = [event for event in events if _workflow_for_type(_event_type(event))[0]]
    status = WorkflowStatus(subject_id=subject_id, next_allowed=[])
    if not relevant:
        return status

    workflows = {_workflow_for_type(_event_type(event))[0] for event in relevant}
    if len(workflows) != 1:
        status.exists = True
        status.valid = False
        status.message = f"Subject {subject_id} mixes product and circular workflow events."
        return status

    workflow = next(iter(workflows))
    steps = PRODUCT_STEPS if workflow == "product" else CIRCULAR_STEPS
    labels = PRODUCT_LABELS if workflow == "product" else CIRCULAR_LABELS
    status.workflow = workflow
    status.exists = True
    status.total_steps = len(steps)
    current = -1
    accepted_custody = False

    for event in relevant:
        event_type = _event_type(event)
        idx = steps.index(event_type)
        payload = _event_payload(event)

        if workflow == "product":
            if idx != current + 1:
                expected = steps[min(current + 1, len(steps) - 1)]
                status.valid = False
                status.message = (
                    f"Existing history is out of order: found {event_type} "
                    f"while expecting {expected}."
                )
                return status
            current = idx
        else:
            if event_type == "residue_custody" and current == 1:
                accepted_custody = accepted_custody or bool(payload.get("accepted"))
                status.last_event_id = getattr(event, "event_id", "")
                status.updated_at = _event_timestamp(event)
                continue
            if event_type == "useful_output" and current == 3:
                status.last_event_id = getattr(event, "event_id", "")
                status.updated_at = _event_timestamp(event)
                continue
            if event_type == "return_or_sale" and current == 4:
                status.last_event_id = getattr(event, "event_id", "")
                status.updated_at = _event_timestamp(event)
                continue
            if idx != current + 1:
                expected = steps[min(current + 1, len(steps) - 1)]
                status.valid = False
                status.message = (
                    f"Existing circular history is out of order: found {event_type} "
                    f"while expecting {expected}."
                )
                return status
            current = idx
            if event_type == "residue_custody":
                accepted_custody = bool(payload.get("accepted"))
            if event_type == "residue_generation":
                status.origin_batch = str(payload.get("origin_batch", ""))

        status.last_event_id = getattr(event, "event_id", "")
        status.updated_at = _event_timestamp(event)

    if current >= 0:
        status.current_step = steps[current]
        status.current_label = labels[steps[current]]
        status.current_step_number = current + 1
        status.progress_pct = round((current + 1) * 100 / len(steps), 2)

    if current == len(steps) - 1:
        status.complete = True
        status.message = "Workflow complete."
        status.next_allowed = ["consumer_verification"] if workflow == "product" else []
        return status

    if workflow == "circular":
        if current == 1:
            if accepted_custody:
                status.next_allowed = ["valorization"]
                status.message = "Residue accepted. Valorization is the next required step."
            else:
                status.next_allowed = ["residue_custody"]
                status.message = "Waiting for an accepted custody record before valorization."
            return status
        if current == 3:
            status.next_allowed = ["useful_output", "return_or_sale"]
            status.message = "Record another useful output or continue to return or sale."
            return status
        if current == 4:
            status.next_allowed = ["return_or_sale", "env_accounting"]
            status.message = "Record another destination or complete environmental accounting."
            return status

    status.next_allowed = [steps[current + 1]]
    status.message = f"Next required step: {labels[steps[current + 1]]}."
    return status


def statuses_from_events(events: Iterable) -> list[dict]:
    by_subject: dict[str, list] = {}
    for event in events:
        if not _workflow_for_type(_event_type(event))[0]:
            continue
        by_subject.setdefault(getattr(event, "subject_id", ""), []).append(event)
    return [derive_status(subject, by_subject[subject]).to_dict() for subject in sorted(by_subject)]


def transition_allowed(status: dict, event_type: str) -> tuple[bool, str]:
    if event_type in {"correction", "reward_issued", "review_flag", "review_resolution"}:
        return True, ""
    if event_type == "consumer_verification":
        if status.get("workflow") == "product" and status.get("complete"):
            return True, ""
        return False, "Consumer verification is available only after distribution."
    if not status.get("exists"):
        first = "cultivation" if event_type in PRODUCT_STEPS else "residue_generation"
        if event_type == first:
            return True, ""
        return False, f"The workflow has not started. First required event: {first}."
    if event_type in (status.get("next_allowed") or []):
        return True, ""
    next_text = " or ".join(status.get("next_allowed") or []) or "none"
    return False, (
        f"Current step is {status.get('current_step')}; "
        f"next allowed event is {next_text}; cannot submit {event_type}."
    )
