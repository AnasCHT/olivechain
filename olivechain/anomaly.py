"""Analytical evidence layer: anomaly detection.

Document: "anomaly detection for implausible yields, dates, weights, residue
ratios, duplicate records, or conflicting custody events."

Principal-risk handling: "Missing or suspicious data should initially trigger
review, not automatic punishment" — findings become REVIEW_FLAG events for
the governance body, never automatic penalties. Also targets "incentive
gaming: actors may split batches, duplicate events, manipulate weights."
"""
from __future__ import annotations

from dataclasses import dataclass

from .ledger import Ledger
from .models import EventType

# Governance parameters (to be ratified in pilot stage 2). Literature-typical
# ranges used as defaults; olive oil extraction yield ~10-25% by mass, and
# pomace typically 35-60% of milled mass depending on system.
PLAUSIBLE_OIL_YIELD = (0.05, 0.30)      # litres of oil per kg of olives
PLAUSIBLE_RESIDUE_RATIO = (0.20, 0.90)  # kg residue per kg olives milled
OIL_DENSITY = 0.916                      # kg/l


@dataclass
class Finding:
    rule: str
    subject_event: str
    detail: str


def scan(ledger: Ledger) -> list[Finding]:
    findings: list[Finding] = []
    findings += _implausible_yields(ledger)
    findings += _duplicate_records(ledger)
    findings += _conflicting_custody(ledger)
    findings += _residue_ratio(ledger)
    return findings


def _implausible_yields(ledger: Ledger) -> list[Finding]:
    out = []
    for ev in ledger.iter_type(EventType.MILLING):
        if ev.superseded_by:
            continue
        p = ledger.effective_payload(ev)
        received = float(p.get("received_kg", 0))
        oil_l = float(p.get("oil_yield_l", 0))
        if received <= 0:
            continue
        ratio = oil_l / received
        lo, hi = PLAUSIBLE_OIL_YIELD
        if not (lo <= ratio <= hi):
            out.append(Finding(
                rule="implausible_oil_yield",
                subject_event=ev.event_id,
                detail=f"{oil_l} l oil from {received} kg olives (ratio {ratio:.3f} l/kg outside [{lo}, {hi}])",
            ))
    return out


def _residue_ratio(ledger: Ledger) -> list[Finding]:
    out = []
    for ev in ledger.iter_type(EventType.MILLING):
        if ev.superseded_by:
            continue
        p = ledger.effective_payload(ev)
        received = float(p.get("received_kg", 0))
        declared = p.get("residues_declared", [])
        total_res = sum(float(r.get("weight_kg", 0)) for r in declared)
        if received <= 0 or total_res == 0:
            continue
        ratio = total_res / received
        lo, hi = PLAUSIBLE_RESIDUE_RATIO
        if not (lo <= ratio <= hi):
            out.append(Finding(
                rule="implausible_residue_ratio",
                subject_event=ev.event_id,
                detail=f"{total_res} kg residues from {received} kg olives (ratio {ratio:.2f} outside [{lo}, {hi}])",
            ))
    return out


def _duplicate_records(ledger: Ledger) -> list[Finding]:
    """Same actor, type, subject and near-identical payload — likely a
    duplicated event submitted to farm rewards."""
    seen: dict[tuple, str] = {}
    out = []
    for ev in ledger.all():
        if ev.event_type in (EventType.CONSUMER_VERIFICATION.value, EventType.CORRECTION.value):
            continue
        key = (ev.event_type, ev.subject_id, ev.actor_org,
               tuple(sorted((k, str(v)) for k, v in ev.payload.items())))
        if key in seen and ev.superseded_by is None:
            out.append(Finding(
                rule="duplicate_record",
                subject_event=ev.event_id,
                detail=f"duplicates event {seen[key]}",
            ))
        else:
            seen.setdefault(key, ev.event_id)
    return out


def _conflicting_custody(ledger: Ledger) -> list[Finding]:
    """The same residue lot transferred to two different receivers with no
    intermediate custody back — conflicting custody claims."""
    out = []
    holders: dict[str, str] = {}
    for ev in ledger.all():
        if ev.event_type != EventType.RESIDUE_CUSTODY.value or ev.superseded_by:
            continue
        p = ledger.effective_payload(ev)
        rid = p["residue_id"]
        frm, to = p["from_org"], p["to_org"]
        current = holders.get(rid)
        if current is not None and frm != current:
            out.append(Finding(
                rule="conflicting_custody",
                subject_event=ev.event_id,
                detail=f"{rid}: transfer claimed from {frm} but current holder is {current}",
            ))
        holders[rid] = to
    return out
