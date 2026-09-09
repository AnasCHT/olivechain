"""Controlled field-pilot scenario (pilot stage 4, in silico).

Intentionally narrow, per the document: one cooperative, one mill, one
laboratory, one residue valorization partner, a limited number of batches.
Runs both loops end-to-end, then demonstrates the safeguards:
  - a signed correction that supersedes (not overwrites) a bad weight
  - an implausible-yield anomaly -> review flag -> resolution
  - mass-balance gating of rewards
  - detection of post-hoc tampering with ledger and off-chain evidence
Writes the batch passport JSON for the frontend.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from olivechain import (Registry, Ledger, EvidenceStore, IncentiveEngine,
                        build_passport, reconcile_residue, Role, EventType)
from olivechain import anomaly

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA, exist_ok=True)
for f in ("ledger.jsonl", "registry.json"):
    p = os.path.join(DATA, f)
    if os.path.exists(p):
        os.remove(p)

registry = Registry(os.path.join(DATA, "registry.json"))
ledger = Ledger(registry, os.path.join(DATA, "ledger.jsonl"))
store = EvidenceStore(os.path.join(os.path.dirname(__file__), "..", "evidence_store"))

# ---- 1. Register the pilot consortium (identity layer) ----
keys = {}
keys["coop"] = registry.register("coop-zaytoun", "Zaytoun Cooperative", [Role.FARMER])
keys["truck"] = registry.register("trans-atlas", "Atlas Transport", [Role.COLLECTOR])
keys["mill"] = registry.register("mill-fes", "Fès Olive Mill", [Role.MILL])
keys["lab"] = registry.register("lab-inra", "INRA Quality Laboratory", [Role.LABORATORY])
keys["bottler"] = registry.register("bottle-rif", "Rif Bottling Co.", [Role.BOTTLER])
keys["retail"] = registry.register("retail-souk", "Souk Retail Group", [Role.DISTRIBUTOR, Role.RETAILER])
keys["proc"] = registry.register("proc-verde", "Verde Valorization", [Role.PROCESSOR])
keys["gov"] = registry.register("gov-consortium", "OliveChain Consortium Authority", [Role.AUTHORITY])
keys["consumer"] = registry.register("consumer-app", "Consumer Passport App", [Role.CONSUMER])

BATCH = "BATCH-2025-001"
POMACE = "RES-POMACE-001"
LEAVES = "RES-LEAVES-001"
t = time.time() - 86400 * 30  # pilot started a month ago


def ev(etype, subject, actor, payload, key, evidence=None, dt=0.0):
    global t
    t += 3600 * 6 + dt
    return ledger.append(etype, subject, actor, payload, key, evidence=evidence, timestamp=t)


# ---- 2. Loop 1: product trust from field to bottle ----
cert = store.put("organic_certificate.pdf", b"%PDF- demo organic certification for plot P-14, cultivar Picholine")
ev(EventType.CULTIVATION, BATCH, "coop-zaytoun", {
    "farm_id": "farm-07", "plot_id": "P-14", "cultivar": "Picholine Marocaine",
    "practices": ["organic", "drip_irrigation"], "certifications": ["EU-organic"],
    "environmental_indicators": {"water_use_m3_per_ha": 1200},
}, keys["coop"], evidence=[cert])

ev(EventType.HARVEST, BATCH, "coop-zaytoun", {
    "date": "2025-11-04", "quantity_kg": 5000, "method": "hand_picked",
    "maturity": "veraison 3.5/7", "location": "34.02N,-5.00W",
}, keys["coop"])

# Collector records 5050 kg by mistake -> corrected later
bad = ev(EventType.COLLECTION_TRANSPORT, BATCH, "trans-atlas", {
    "from_org": "coop-zaytoun", "to_org": "mill-fes", "weight_kg": 5050,
    "container_ids": ["CT-11", "CT-12"], "transport_conditions": {"max_temp_c": 19},
}, keys["truck"])

photo = store.put("weighbridge_photo.jpg", b"\xff\xd8\xff demo weighbridge photo: 4980 kg")
ev(EventType.CORRECTION, BATCH, "trans-atlas", {
    "supersedes_event": bad.event_id,
    "reason": "weighbridge re-read: tare not deducted",
    "corrected_payload": {"weight_kg": 4980},
}, keys["truck"], evidence=[photo])

milling = ev(EventType.MILLING, BATCH, "mill-fes", {
    "received_kg": 4980, "extraction_method": "two_phase_cold",
    "temperature_c": 26, "processing_hours": 9, "oil_yield_l": 980,
    "storage": "inert-gas tank T3",
    "residues_declared": [
        {"residue_id": POMACE, "residue_type": "alpeorujo", "weight_kg": 2900},
        {"residue_id": LEAVES, "residue_type": "leaves", "weight_kg": 240},
    ],
}, keys["mill"])

lab_report = store.put("lab_report_B2025001.pdf", b"%PDF- acidity 0.24%, peroxide 7.1, K232 1.68, panel: fruity/bitter/pungent balanced")
ev(EventType.LAB_VERIFICATION, BATCH, "lab-inra", {
    "quality_class": "organic_extra_virgin",
    "results": {"free_acidity_pct": 0.24, "peroxide_meq_kg": 7.1,
                "K232": 1.68, "sensory_defects": 0, "contaminants": "none_detected"},
    "authenticity": "profile consistent with declared cultivar and region",
}, keys["lab"], evidence=[lab_report])

ev(EventType.BOTTLING, BATCH, "bottle-rif", {
    "lot_id": "LOT-88", "bottle_count": 1900, "fill_date": "2025-11-20",
    "packaging": "dark glass 500ml", "label_claims": ["organic extra virgin", "single estate"],
}, keys["bottler"])

ev(EventType.DISTRIBUTION_RETAIL, BATCH, "retail-souk", {
    "from_org": "bottle-rif", "to_org": "retail-souk",
    "destination": "Rabat + Casablanca stores", "shipment_conditions": {"max_temp_c": 22},
}, keys["retail"])

# ---- 3. Loop 2: circular recovery and valorization ----
ev(EventType.RESIDUE_GENERATION, POMACE, "mill-fes", {
    "residue_type": "alpeorujo", "weight_kg": 2900, "moisture_pct": 62,
    "quality": "fresh", "contamination": "none", "origin_batch": BATCH,
}, keys["mill"])

scale = store.put("scale_ticket_pomace.csv", b"lot,kg\nRES-POMACE-001,2895")
ev(EventType.RESIDUE_CUSTODY, POMACE, "trans-atlas", {
    "residue_id": POMACE, "weight_kg": 2895, "measurement_method": "calibrated_scale_SC9",
    "from_org": "mill-fes", "to_org": "proc-verde", "accepted": True,
    "transporter": "trans-atlas",
}, keys["truck"], evidence=[scale])

ev(EventType.VALORIZATION, POMACE, "proc-verde", {
    "residue_id": POMACE, "input_kg": 2880, "method": "polyphenol_extraction_then_composting",
    "outputs": [
        {"output_type": "polyphenols_g", "quantity": 4100},
        {"output_type": "compost_kg", "quantity": 1750},
        {"output_type": "bioenergy_kwh", "quantity": 610},
    ],
    "rejected_kg": 55,
}, keys["proc"])

ev(EventType.USEFUL_OUTPUT, POMACE, "proc-verde", {
    "residue_id": POMACE, "output_type": "compost_kg", "quantity": 1750, "unit": "kg",
    "verification": "third-party sampled, C/N 18",
}, keys["proc"])

ev(EventType.RETURN_OR_SALE, POMACE, "proc-verde", {
    "residue_id": POMACE, "output_type": "compost_kg", "quantity": 1200, "unit": "kg",
    "destination": "coop-zaytoun (soil amendment return)",
}, keys["proc"])

rec = reconcile_residue(ledger, POMACE)
ev(EventType.ENV_ACCOUNTING, POMACE, "gov-consortium", {
    "residue_id": POMACE, "recovery_pct": rec.recovery_pct,
    "avoided_disposal_kg": rec.transformed_kg - rec.rejected_kg,
    "baseline": "open-air pomace disposal (pre-pilot)",
    "note": "LCA pending; mass recovery does not by itself prove lower life-cycle impact",
}, keys["gov"])

# Leaves lot: generated but never valorized -> mass balance must FAIL and block rewards
ev(EventType.RESIDUE_GENERATION, LEAVES, "mill-fes", {
    "residue_type": "leaves", "weight_kg": 240, "moisture_pct": 30,
    "quality": "mixed", "contamination": "soil traces", "origin_batch": BATCH,
}, keys["mill"])
ev(EventType.RESIDUE_CUSTODY, LEAVES, "trans-atlas", {
    "residue_id": LEAVES, "weight_kg": 238, "measurement_method": "calibrated_scale_SC9",
    "from_org": "mill-fes", "to_org": "proc-verde", "accepted": True,
}, keys["truck"])

# ---- 4. A second, suspicious batch: implausible yield -> review, not punishment ----
BATCH2 = "BATCH-2025-002"
ev(EventType.HARVEST, BATCH2, "coop-zaytoun", {
    "date": "2025-11-10", "quantity_kg": 1000, "method": "mechanical", "location": "34.02N,-5.01W",
}, keys["coop"])
sus = ev(EventType.MILLING, BATCH2, "mill-fes", {
    "received_kg": 1000, "extraction_method": "two_phase_cold", "temperature_c": 27,
    "oil_yield_l": 480,  # 48% yield: implausible
    "residues_declared": [],
}, keys["mill"])

# ---- 5. Consumer scans ----
for _ in range(3):
    ev(EventType.CONSUMER_VERIFICATION, BATCH, "consumer-app",
       {"channel": "qr_scan"}, keys["consumer"], dt=120)

# ---- 6. Governance: anomaly scan -> flags -> resolution ----
engine = IncentiveEngine(ledger, "gov-consortium", keys["gov"])
findings = anomaly.scan(ledger)
print(f"\n=== Anomaly scan: {len(findings)} finding(s) ===")
flag_ids = {}
for f in findings:
    print(f"  [{f.rule}] {f.detail}")
    fl = engine.flag(f.subject_event, f.rule, f.detail)
    flag_ids[f.subject_event] = fl.event_id

# ---- 7. Rewards: only verified, mass-balanced actions pay out ----
issued = engine.run()
print(f"\n=== Rewards issued: {len(issued)} ===")
for i in issued:
    print(f"  {i['recipient']:16s} +{i['amount']:3d} EcoPoints  ({i['rule']})")
print("\nBalances:", json.dumps(engine.balances(), indent=2))

# Flagged milling event earned no 'prompt_records' reward:
rewarded_bases = {b for e in ledger.iter_type(EventType.REWARD_ISSUED)
                  for b in e.payload["basis_events"]}
assert sus.event_id not in rewarded_bases, "flagged event must not be rewarded"
print("\nFlagged milling event correctly excluded from rewards (review first).")

# Governance resolves the flag (mill re-measured: data entry error, corrected)
ev(EventType.CORRECTION, BATCH2, "mill-fes", {
    "supersedes_event": sus.event_id, "reason": "decimal error at data entry",
    "corrected_payload": {"oil_yield_l": 180},
}, keys["mill"])
engine.resolve(flag_ids[sus.event_id], "corrected", "mill submitted signed correction; yield now plausible")

# ---- 8. Mass balance summary ----
for rid in (POMACE, LEAVES):
    r = reconcile_residue(ledger, rid)
    print(f"\n=== Mass balance {rid} ===")
    print(f"  generated {r.generated_kg} kg | transferred {r.transferred_kg} | "
          f"accepted {r.accepted_kg} | transformed {r.transformed_kg} | recovery {r.recovery_pct}%")
    print(f"  balanced: {r.balanced}" + (f" | issues: {r.issues}" if r.issues else ""))

# ---- 9. Full audit + tamper demonstration ----
ok, problems = ledger.verify_chain()
print(f"\n=== Ledger audit: valid={ok} ({len(ledger)} events) ===")
assert ok, problems

target = ledger.all()[4]
original = target.payload.get("received_kg")
if "received_kg" in target.payload:
    target.payload["received_kg"] = 99999
ok2, problems2 = ledger.verify_chain()
print(f"After in-memory tampering with a milling weight: valid={ok2}")
for p in problems2[:2]:
    print("  ", p)
assert not ok2
target.payload["received_kg"] = original  # restore

with open(cert["uri"], "ab") as f:
    f.write(b" TAMPERED")
print("After appending bytes to the off-chain certificate:",
      "intact" if store.verify(cert) else "SUBSTITUTION DETECTED")
assert not store.verify(cert)

# ---- 10. Emit the consumer passport for the frontend ----
passport = build_passport(ledger, BATCH, store)
out = os.path.join(DATA, "passport_BATCH-2025-001.json")
with open(out, "w") as f:
    json.dump(passport, f, indent=2, default=str)
print(f"\nPassport written to {out}")
print(f"Passport ledger_verified={passport['ledger_verified']}, "
      f"stages={len(passport['stages'])}, circular lots={len(passport['circular'])}, "
      f"rewards={len(passport['rewards'])}, scans={passport['consumer_scans']}")
