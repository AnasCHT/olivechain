"""Incentives and EcoTokens.

Document: "The incentive mechanism is intended to change behavior, not create
a speculative cryptocurrency. Rewards should be issued only for actions that
are both valuable and verifiable." Implemented as a NON-TRANSFERABLE
reputation ledger by default ("a non-transferable reputation score may be
more appropriate than a tradable token ... because it reduces speculation and
links benefits to the responsible organization"). Whether transferable tokens
are ever enabled is a regulatory/governance decision outside this codebase
(risk: "Regulatory and token risk").

Gate (roadmap step 6): rewards touching residue lots are only issued after
mass-balance reconciliation passes and no open review flags concern the
basis events. Suspicious data triggers REVIEW_FLAG events, not penalties.
"""
from __future__ import annotations

from dataclasses import dataclass

from .ledger import Ledger
from .massbalance import reconcile_residue
from .models import EventType


@dataclass(frozen=True)
class RewardRule:
    rule_id: str
    description: str
    event_type: EventType
    amount: int
    requires_mass_balance: bool = False


# The reward catalogue mirrors the document's list of rewardable actions.
REWARD_RULES: list[RewardRule] = [
    RewardRule("residue_delivery", "delivering a measured residue quantity to an authorized processor",
               EventType.RESIDUE_CUSTODY, amount=10, requires_mass_balance=False),
    RewardRule("quality_criteria", "meeting validated quality or sustainability criteria",
               EventType.LAB_VERIFICATION, amount=15),
    RewardRule("soil_return", "returning recovered compost, biochar, or fertilizer to agricultural use",
               EventType.RETURN_OR_SALE, amount=20, requires_mass_balance=True),
    RewardRule("verified_recovery", "producing independently verified renewable energy or recovered material",
               EventType.USEFUL_OUTPUT, amount=25, requires_mass_balance=True),
    RewardRule("prompt_records", "completing reliable records promptly",
               EventType.MILLING, amount=5),
    RewardRule("circular_participation", "participating in packaging return, verified feedback, or other circular activities",
               EventType.CONSUMER_VERIFICATION, amount=1),
]

RULES_BY_EVENT: dict[str, list[RewardRule]] = {}
for r in REWARD_RULES:
    RULES_BY_EVENT.setdefault(r.event_type.value, []).append(r)


def _already_rewarded(ledger: Ledger, basis_event_id: str, rule_id: str) -> bool:
    for ev in ledger.iter_type(EventType.REWARD_ISSUED):
        p = ev.payload
        if p["reward_rule"] == rule_id and basis_event_id in p["basis_events"]:
            return True
    return False


def open_flags(ledger: Ledger) -> set[str]:
    """Events under an unresolved review flag are not rewardable yet."""
    flagged: dict[str, str] = {}
    for ev in ledger.iter_type(EventType.REVIEW_FLAG):
        flagged[ev.payload["subject_event"]] = ev.event_id
    resolved = {
        ev.payload["flag_event"]
        for ev in ledger.iter_type(EventType.REVIEW_RESOLUTION)
    }
    return {subj for subj, flag_id in flagged.items() if flag_id not in resolved}


def due_rewards(ledger: Ledger) -> list[dict]:
    """Every reward that is currently due and verifiable, WITHOUT issuing it.
    Pure computation over the ledger: the same gates as issuance (idempotency,
    open review flags, mass balance, quality class) so the authority can sign
    the issuance events itself — the server holds no signing key."""
    due = []
    flagged = open_flags(ledger)
    for ev in ledger.all():
        if ev.superseded_by or ev.event_type not in RULES_BY_EVENT:
            continue
        for rule in RULES_BY_EVENT[ev.event_type]:
            if _already_rewarded(ledger, ev.event_id, rule.rule_id):
                continue
            if ev.event_id in flagged:
                continue  # review first, never reward flagged data
            if rule.requires_mass_balance:
                rid = ev.payload.get("residue_id")
                rec = reconcile_residue(ledger, rid) if rid else None
                if rec is None or not rec.balanced:
                    continue  # mass balance must pass before rewards
            if rule.rule_id == "quality_criteria":
                if ev.payload.get("quality_class") not in ("extra_virgin", "organic_extra_virgin"):
                    continue
            due.append({
                "recipient": ev.actor_org,
                "amount": rule.amount,
                "reward_rule": rule.rule_id,
                "rule_description": rule.description,
                "basis_events": [ev.event_id],
                "transferable": False,
            })
    return due


class IncentiveEngine:
    """Reads the ledger; issues REWARD_ISSUED events through the authority's
    signature so every reward is itself an auditable, signed ledger record."""

    def __init__(self, ledger: Ledger, authority_org: str, authority_key):
        self.ledger = ledger
        self.authority_org = authority_org
        self.authority_key = authority_key

    # ------------------------------------------------------------- balances
    def balances(self) -> dict[str, int]:
        bal: dict[str, int] = {}
        for ev in self.ledger.iter_type(EventType.REWARD_ISSUED):
            if ev.superseded_by:
                continue
            p = ev.payload
            bal[p["recipient"]] = bal.get(p["recipient"], 0) + int(p["amount"])
        return bal

    def _open_flags(self) -> set[str]:
        return open_flags(self.ledger)

    # ------------------------------------------------------------- issuance
    def run(self) -> list[dict]:
        """Scan the ledger and issue every reward that is due and verifiable.
        Idempotent: an event is rewarded at most once per rule."""
        issued = []
        for d in due_rewards(self.ledger):
            reward = self.ledger.append(
                EventType.REWARD_ISSUED,
                subject_id=d["recipient"],
                actor_org=self.authority_org,
                payload={
                    "recipient": d["recipient"],
                    "amount": d["amount"],
                    "reward_rule": d["reward_rule"],
                    "basis_events": d["basis_events"],
                    "transferable": False,
                },
                keypair=self.authority_key,
            )
            issued.append({"reward": reward.event_id, "rule": d["reward_rule"],
                           "recipient": d["recipient"], "amount": d["amount"]})
        return issued

    # ------------------------------------------------------------- review flow
    def flag(self, subject_event: str, rule: str, detail: str):
        return self.ledger.append(
            EventType.REVIEW_FLAG, subject_id=subject_event,
            actor_org=self.authority_org,
            payload={"subject_event": subject_event, "rule": rule, "detail": detail},
            keypair=self.authority_key,
        )

    def resolve(self, flag_event: str, decision: str, rationale: str):
        """decision: 'cleared' | 'corrected' | 'penalized' — penalties only
        after agreed rules, evidence, and this appeal-capable process."""
        return self.ledger.append(
            EventType.REVIEW_RESOLUTION, subject_id=flag_event,
            actor_org=self.authority_org,
            payload={"flag_event": flag_event, "decision": decision, "rationale": rationale},
            keypair=self.authority_key,
        )
