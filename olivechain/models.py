"""Domain model for OliveChain.

Encodes the document's shared ontology (roadmap step 3): batches, custody,
laboratory evidence, residues, transformations, outputs, and rewards.
"""
from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    FARMER = "farmer"                 # farmers and cooperatives
    COLLECTOR = "collector"           # collectors and transporters
    MILL = "mill"                     # mills and extractors
    LABORATORY = "laboratory"         # laboratories and certifiers
    BOTTLER = "bottler"
    DISTRIBUTOR = "distributor"
    RETAILER = "retailer"
    PROCESSOR = "processor"           # residue processors and recyclers
    AUTHORITY = "authority"           # public authority / consortium governance
    CONSUMER = "consumer"


class EventType(str, Enum):
    # ---- Loop 1: product trust from field to bottle (8 stages) ----
    CULTIVATION = "cultivation"                 # farm, plot, cultivar, practices, certifications
    HARVEST = "harvest"                         # date, quantity, method, maturity, actor, location
    COLLECTION_TRANSPORT = "collection_transport"  # custody transfer, containers, weight, timestamps
    MILLING = "milling"                         # received qty, method, temperature, yield, residues generated
    LAB_VERIFICATION = "lab_verification"       # chemical/sensory/contaminant/authenticity, signed lab identity
    BOTTLING = "bottling"                       # lot composition, bottle ids, packaging, filling date, claims
    DISTRIBUTION_RETAIL = "distribution_retail" # custody events, shipment conditions, destination, receipt
    CONSUMER_VERIFICATION = "consumer_verification"  # QR/NFC scan of the passport

    # ---- Loop 2: circular recovery and valorization (6 stages) ----
    RESIDUE_GENERATION = "residue_generation"   # type, weight, moisture, quality, contamination, origin
    RESIDUE_CUSTODY = "residue_custody"         # measurement method, party, transporter, destination, acceptance
    VALORIZATION = "valorization"               # conversion method, inputs, outputs, rejected fractions
    USEFUL_OUTPUT = "useful_output"             # bioenergy, compost, biochar, polyphenols, fertilizer...
    RETURN_OR_SALE = "return_or_sale"           # distribution of output, incl. return of soil amendments
    ENV_ACCOUNTING = "env_accounting"           # mass balance, recovery %, avoided disposal, emissions

    # ---- Governance / system ----
    CORRECTION = "correction"                   # signed correction superseding a prior event (audit preserved)
    REWARD_ISSUED = "reward_issued"             # EcoToken / reputation issuance (only after verification)
    REVIEW_FLAG = "review_flag"                 # suspicious data -> review, not automatic punishment
    REVIEW_RESOLUTION = "review_resolution"     # governance decision on a flag (with appeal trail)


# Role-based permissions: which roles may submit which event types
# (document: "Identity evidence: authenticated organizations, role-based
# permissions, digital signatures, and accountable users").
PERMISSIONS: dict[EventType, set[Role]] = {
    EventType.CULTIVATION: {Role.FARMER},
    EventType.HARVEST: {Role.FARMER},
    EventType.COLLECTION_TRANSPORT: {Role.COLLECTOR},
    EventType.MILLING: {Role.MILL},
    EventType.LAB_VERIFICATION: {Role.LABORATORY},
    EventType.BOTTLING: {Role.BOTTLER},
    EventType.DISTRIBUTION_RETAIL: {Role.DISTRIBUTOR, Role.RETAILER},
    EventType.CONSUMER_VERIFICATION: {Role.CONSUMER, Role.RETAILER},
    EventType.RESIDUE_GENERATION: {Role.MILL},
    EventType.RESIDUE_CUSTODY: {Role.COLLECTOR, Role.PROCESSOR},
    EventType.VALORIZATION: {Role.PROCESSOR},
    EventType.USEFUL_OUTPUT: {Role.PROCESSOR},
    EventType.RETURN_OR_SALE: {Role.PROCESSOR, Role.DISTRIBUTOR},
    EventType.ENV_ACCOUNTING: {Role.AUTHORITY, Role.PROCESSOR},
    EventType.CORRECTION: set(Role),  # any authenticated actor may correct its own events
    EventType.REWARD_ISSUED: {Role.AUTHORITY},
    EventType.REVIEW_FLAG: {Role.AUTHORITY},
    EventType.REVIEW_RESOLUTION: {Role.AUTHORITY},
}

# Required payload fields per event type (integration layer: standardized
# event schemas). Kept minimal on-chain; bulky evidence goes off-chain and
# is referenced by hash.
REQUIRED_FIELDS: dict[EventType, list[str]] = {
    EventType.CULTIVATION: ["farm_id", "plot_id", "cultivar", "practices"],
    EventType.HARVEST: ["date", "quantity_kg", "method", "location"],
    EventType.COLLECTION_TRANSPORT: ["from_org", "to_org", "weight_kg", "container_ids"],
    EventType.MILLING: [
        "received_kg", "extraction_method", "temperature_c",
        "oil_yield_l", "residues_declared",
    ],
    EventType.LAB_VERIFICATION: ["quality_class", "results"],
    EventType.BOTTLING: ["lot_id", "bottle_count", "fill_date", "label_claims"],
    EventType.DISTRIBUTION_RETAIL: ["from_org", "to_org", "destination"],
    EventType.CONSUMER_VERIFICATION: ["channel"],
    EventType.RESIDUE_GENERATION: ["residue_type", "weight_kg", "moisture_pct", "origin_batch"],
    EventType.RESIDUE_CUSTODY: [
        "residue_id", "weight_kg", "measurement_method", "from_org", "to_org", "accepted",
    ],
    EventType.VALORIZATION: ["residue_id", "input_kg", "method", "outputs", "rejected_kg"],
    EventType.USEFUL_OUTPUT: ["residue_id", "output_type", "quantity", "unit"],
    EventType.RETURN_OR_SALE: ["residue_id", "output_type", "quantity", "unit", "destination"],
    EventType.ENV_ACCOUNTING: ["residue_id", "recovery_pct", "avoided_disposal_kg"],
    EventType.CORRECTION: ["supersedes_event", "reason", "corrected_payload"],
    EventType.REWARD_ISSUED: ["recipient", "amount", "reward_rule", "basis_events"],
    EventType.REVIEW_FLAG: ["subject_event", "rule", "detail"],
    EventType.REVIEW_RESOLUTION: ["flag_event", "decision", "rationale"],
}

RESIDUE_TYPES = {
    "pomace", "alpeorujo", "stones", "leaves", "pruning", "wastewater",
}

OUTPUT_TYPES = {
    "bioenergy_kwh", "compost_kg", "biochar_kg", "polyphenols_g",
    "fertilizer_kg", "feedstock_kg", "adsorbent_kg",
}

# Events whose ambient environmental context must be fetched by the
# server-side external-data oracle. This data validates conditions near the
# declared location; it does not replace physical process or transport sensors.
EXTERNAL_DATA_REQUIRED: set[EventType] = {
    EventType.CULTIVATION,
    EventType.HARVEST,
    EventType.COLLECTION_TRANSPORT,
    EventType.DISTRIBUTION_RETAIL,
    EventType.RESIDUE_CUSTODY,
}
