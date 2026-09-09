"""Mass-balance reconciliation for Loop 2.

Document: "This loop must preserve material balance. Rewards cannot be based
only on a declaration that waste was recycled. The system should reconcile
the quantity and characteristics of residues created, transported, accepted,
transformed, and converted into outputs."

Roadmap step 6: "Implement mass-balance and anomaly rules before enabling
rewards" — the incentives module refuses to issue rewards for a residue lot
until this reconciliation passes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .ledger import Ledger
from .models import EventType


# Tolerance for measurement error and moisture loss between stages.
# The exact figure is a governance parameter to be agreed in pilot stage 2
# ("Specify the governance and data model"); 5% is a placeholder default.
DEFAULT_TOLERANCE = 0.05


@dataclass
class Reconciliation:
    residue_id: str
    generated_kg: float = 0.0
    transferred_kg: float = 0.0
    accepted_kg: float = 0.0
    transformed_kg: float = 0.0
    rejected_kg: float = 0.0
    outputs: dict = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    @property
    def balanced(self) -> bool:
        return not self.issues

    @property
    def recovery_pct(self) -> float:
        if self.generated_kg <= 0:
            return 0.0
        return round(100.0 * self.transformed_kg / self.generated_kg, 2)


def reconcile_residue(ledger: Ledger, residue_id: str, tolerance: float = DEFAULT_TOLERANCE) -> Reconciliation:
    rec = Reconciliation(residue_id=residue_id)
    events = ledger.for_subject(residue_id)  # superseded events excluded

    for ev in events:
        p = ledger.effective_payload(ev)
        t = ev.event_type
        if t == EventType.RESIDUE_GENERATION.value:
            rec.generated_kg += float(p["weight_kg"])
        elif t == EventType.RESIDUE_CUSTODY.value:
            rec.transferred_kg += float(p["weight_kg"])
            if p.get("accepted"):
                rec.accepted_kg += float(p["weight_kg"])
        elif t == EventType.VALORIZATION.value:
            rec.transformed_kg += float(p["input_kg"])
            rec.rejected_kg += float(p.get("rejected_kg", 0))
            for o in p.get("outputs", []):
                key = o["output_type"]
                rec.outputs[key] = rec.outputs.get(key, 0) + float(o["quantity"])

    def within(a: float, b: float) -> bool:
        if max(a, b) == 0:
            return True
        return abs(a - b) / max(a, b) <= tolerance

    if rec.generated_kg == 0:
        rec.issues.append("no residue generation recorded")
    if rec.transferred_kg and not within(rec.generated_kg, rec.transferred_kg):
        rec.issues.append(
            f"transfer/generation mismatch: generated {rec.generated_kg}kg, transferred {rec.transferred_kg}kg"
        )
    if rec.accepted_kg and not within(rec.transferred_kg, rec.accepted_kg):
        rec.issues.append(
            f"acceptance mismatch: transferred {rec.transferred_kg}kg, accepted {rec.accepted_kg}kg"
        )
    accounted_kg = rec.transformed_kg + rec.rejected_kg
    if accounted_kg and not within(rec.accepted_kg, accounted_kg):
        rec.issues.append(
            "transformation mismatch: "
            f"accepted {rec.accepted_kg}kg, "
            f"transformed {rec.transformed_kg}kg, "
            f"rejected {rec.rejected_kg}kg, "
            f"accounted {accounted_kg}kg"
        )
    if accounted_kg == 0 and rec.accepted_kg > 0:
        rec.issues.append("residue accepted but no valorization recorded")

    return rec
