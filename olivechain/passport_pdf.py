"""Signed PDF passport export.

Renders a batch passport as a one- or two-page PDF and binds it to the ledger
with a cryptographic attestation: the passport issuer signs
{batch_id, content hash, ledger head, height, issued_at} with Ed25519, so the
document is tamper-evident and independently verifiable (see /passport/verify).
A QR code links back to the live verifier — the ledger stays the source of
truth; the PDF is a signed snapshot.

Latin scripts (English, French) only: Arabic would need RTL shaping and a
bundled Arabic font, which the on-screen passport at /m already provides.
"""
from __future__ import annotations

import io
import time
from datetime import datetime, timezone

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .crypto import canonical_json, sha256_hex

GREEN_DEEP = HexColor("#1c2a21")
GREEN_MID = HexColor("#2c4032")
GOLD = HexColor("#c2a24b")
GOLD_SOFT = HexColor("#d9c690")
PAPER = HexColor("#f2efe6")
PAPER2 = HexColor("#e9e4d5")
INK = HexColor("#182019")
INK_SOFT = HexColor("#4d5a4e")
OK = HexColor("#5d8a5e")
WARN = HexColor("#b2703a")
LINE = HexColor("#ddd6c2")
LEAF = HexColor("#7d9270")

# Latin-only labels; French accents render fine in the built-in WinAnsi fonts.
T = {
    "en": {
        "eyebrow": "Verifiable circular olive-oil passport",
        "sub": "From the grove, and back to it.",
        "verified": "Ledger verified", "vfail": "Verification FAILED",
        "scans": "{n} consumer scans",
        "journey": "The journey of this oil",
        "journey_l": "Each step was recorded by the organization that performed it and digitally signed. Corrections supersede — they never erase.",
        "byp": "What happened to the by-products",
        "byp_l": "Residues were weighed, tracked to a recovery partner and reconciled by mass balance — verified, not promised.",
        "recovered": "recovered", "accounted": "{kg} kg of {type}, accounted for",
        "mb_ok": "mass balance verified", "mb_wait": "recovery in progress",
        "rec": "Who earned recognition",
        "rec_l": "EcoPoints are non-transferable credits issued only for verifiable actions.",
        "verify_h": "How to verify this document",
        "verify_l": "Scan the code, or visit the address below, to re-check this batch against the live ledger. This PDF carries a cryptographic signature by the OliveChain passport issuer; any edit to it breaks the signature.",
        "issued": "Issued", "head": "Ledger head", "height": "Chain height",
        "content": "Content hash", "issuer": "Issuer key", "sig": "Signature",
        "batch": "Batch", "signed": "signed", "by": "by",
        "foot": "A ledger cannot taste oil: laboratories, scales and audits provide the physical truth. This record coordinates that evidence and makes later alteration detectable.",
    },
    "fr": {
        "eyebrow": "Passeport circulaire vérifiable de l'huile d'olive",
        "sub": "Du verger, et retour au verger.",
        "verified": "Registre vérifié", "vfail": "Vérification ÉCHOUÉE",
        "scans": "{n} scans consommateurs",
        "journey": "Le parcours de cette huile",
        "journey_l": "Chaque étape a été enregistrée par l'organisation qui l'a réalisée et signée numériquement. Les corrections remplacent — elles n'effacent jamais.",
        "byp": "Ce que sont devenus les sous-produits",
        "byp_l": "Les résidus ont été pesés, suivis jusqu'à un partenaire de valorisation et réconciliés par bilan de masse — vérifié, pas promis.",
        "recovered": "valorisé", "accounted": "{kg} kg de {type}, comptabilisés",
        "mb_ok": "bilan de masse vérifié", "mb_wait": "valorisation en cours",
        "rec": "Qui a été récompensé",
        "rec_l": "Les ÉcoPoints sont des crédits non transférables, émis uniquement pour des actions vérifiables.",
        "verify_h": "Comment vérifier ce document",
        "verify_l": "Scannez le code, ou visitez l'adresse ci-dessous, pour revérifier ce lot face au registre en direct. Ce PDF porte une signature cryptographique de l'émetteur de passeports OliveChain ; toute modification invalide la signature.",
        "issued": "Émis le", "head": "Tête du registre", "height": "Hauteur de chaîne",
        "content": "Empreinte du contenu", "issuer": "Clé de l'émetteur", "sig": "Signature",
        "batch": "Lot", "signed": "signé", "by": "par",
        "foot": "Un registre ne peut pas goûter l'huile : laboratoires, balances et audits fournissent la vérité physique. Ce registre coordonne ces preuves et rend toute altération ultérieure détectable.",
    },
}

STAGE = {
    "en": {"Grown": "Grown", "Harvested": "Harvested", "Collected": "Collected",
           "Milled": "Milled", "Quality verified": "Quality verified",
           "Bottled": "Bottled", "Shipped to market": "Shipped to market"},
    "fr": {"Grown": "Cultivé", "Harvested": "Récolté", "Collected": "Collecté",
           "Milled": "Pressé", "Quality verified": "Qualité vérifiée",
           "Bottled": "Embouteillé", "Shipped to market": "Expédié au marché"},
}

OUT = {
    "en": {"compost_kg": "kg compost", "polyphenols_g": "g polyphenols",
           "bioenergy_kwh": "kWh bioenergy", "biochar_kg": "kg biochar",
           "fertilizer_kg": "kg fertilizer", "feedstock_kg": "kg feedstock",
           "adsorbent_kg": "kg adsorbent"},
    "fr": {"compost_kg": "kg de compost", "polyphenols_g": "g de polyphénols",
           "bioenergy_kwh": "kWh de bioénergie", "biochar_kg": "kg de biochar",
           "fertilizer_kg": "kg d'engrais", "feedstock_kg": "kg de matière première",
           "adsorbent_kg": "kg d'adsorbant"},
}

WHY = {
    "en": {"residue_delivery": "Delivered measured residues to a processor",
           "quality_criteria": "Met validated quality criteria",
           "soil_return": "Returned recovered material to farmland",
           "verified_recovery": "Produced verified recovered material",
           "prompt_records": "Completed reliable records promptly",
           "circular_participation": "Verified circular participation"},
    "fr": {"residue_delivery": "A livré des résidus mesurés à un valorisateur",
           "quality_criteria": "A satisfait aux critères de qualité validés",
           "soil_return": "A restitué la matière valorisée aux terres agricoles",
           "verified_recovery": "A produit une matière valorisée vérifiée",
           "prompt_records": "A complété des enregistrements fiables sans délai",
           "circular_participation": "Participation circulaire vérifiée"},
}


def _facts(lang, ev_type, p):
    """A few human-readable facts per stage, mirroring the on-screen passport."""
    fr = lang == "fr"
    def num(n):
        return f"{n:,}" if isinstance(n, (int, float)) else n
    if ev_type == "cultivation":
        return [("Cultivar" if not fr else "Cultivar", p.get("cultivar")),
                ("Plot" if not fr else "Parcelle", p.get("plot_id")),
                ("Practices" if not fr else "Pratiques", ", ".join(p.get("practices", []) or []))]
    if ev_type == "harvest":
        return [("Date", p.get("date")),
                ("Quantity" if not fr else "Quantité", f"{num(p.get('quantity_kg'))} kg"),
                ("Method" if not fr else "Méthode", str(p.get("method", "")).replace("_", " "))]
    if ev_type == "collection_transport":
        return [("Weight" if not fr else "Poids", f"{num(p.get('weight_kg'))} kg")]
    if ev_type == "milling":
        return [("Olives received" if not fr else "Olives reçues", f"{num(p.get('received_kg'))} kg"),
                ("Oil produced" if not fr else "Huile produite", f"{num(p.get('oil_yield_l'))} L"),
                ("Method" if not fr else "Méthode", str(p.get("extraction_method", "")).replace("_", " "))]
    if ev_type == "lab_verification":
        res = p.get("results", {}) or {}
        return [("Class" if not fr else "Classe", str(p.get("quality_class", "")).replace("_", " ")),
                ("Free acidity" if not fr else "Acidité libre", f"{res.get('free_acidity_pct')} %"),
                ("Defects" if not fr else "Défauts", res.get("sensory_defects"))]
    if ev_type == "bottling":
        return [("Bottles" if not fr else "Bouteilles", num(p.get("bottle_count"))),
                ("Claims" if not fr else "Mentions", " · ".join(p.get("label_claims", []) or []))]
    if ev_type == "distribution_retail":
        return [("Destination", p.get("destination"))]
    return []


class _Doc:
    """Thin y-cursor wrapper over a reportlab canvas with page-break handling."""

    def __init__(self, c: canvas.Canvas):
        self.c = c
        self.w, self.h = A4
        self.margin = 48
        self.y = self.h

    def ensure(self, space):
        if self.y - space < self.margin:
            self.c.showPage()
            self.y = self.h - self.margin

    def heading(self, text):
        self.ensure(48)
        self.y -= 30
        self.c.setFillColor(INK)
        self.c.setFont("Helvetica-Bold", 15)
        self.c.drawString(self.margin, self.y, text)
        self.y -= 6
        self.c.setStrokeColor(GOLD)
        self.c.setLineWidth(1.5)
        self.c.line(self.margin, self.y, self.margin + 60, self.y)
        self.y -= 12

    def para(self, text, color=INK_SOFT, size=9, font="Helvetica", lead=12, width=None):
        self.c.setFillColor(color)
        self.c.setFont(font, size)
        max_w = width or (self.w - 2 * self.margin)
        for line in _wrap(self.c, text, font, size, max_w):
            self.ensure(lead)
            self.y -= lead
            self.c.drawString(self.margin, self.y, line)


def _wrap(c, text, font, size, max_w):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if c.stringWidth(trial, font, size) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def build_passport_pdf(passport: dict, *, signer, issuer_pub: str, head_hash: str,
                       height: int, verify_url: str, lang: str = "en") -> tuple[bytes, dict]:
    """Render the signed PDF and return (pdf_bytes, attestation)."""
    lang = lang if lang in T else "en"
    tr = T[lang]
    issued_at = int(time.time())

    attestation = {
        "type": "olivechain-passport-attestation",
        "version": 1,
        "batch_id": passport["batch_id"],
        "content_sha256": sha256_hex(canonical_json(passport)),
        "ledger_head_hash": head_hash,
        "ledger_height": height,
        "ledger_verified": bool(passport["ledger_verified"]),
        "issued_at": issued_at,
    }
    signature = signer.sign(canonical_json(attestation))

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"OliveChain passport {passport['batch_id']}")
    doc = _Doc(c)
    W = doc.w

    # ---- header band ----
    band_h = 150
    c.setFillColor(GREEN_DEEP)
    c.rect(0, doc.h - band_h, W, band_h, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(doc.margin, doc.h - 42, tr["eyebrow"].upper())
    c.setFillColor(PAPER)
    c.setFont("Helvetica-Bold", 30)
    c.drawString(doc.margin, doc.h - 78, "OliveChain")
    c.setFillColor(PAPER2)
    c.setFont("Helvetica-Oblique", 12)
    c.drawString(doc.margin, doc.h - 96, tr["sub"])
    # batch chip + seal
    c.setFont("Helvetica", 10)
    c.setFillColor(PAPER)
    c.drawString(doc.margin, doc.h - 126, f"{tr['batch']}: {passport['batch_id']}")
    verified = passport["ledger_verified"]
    seal = tr["verified"] if verified else tr["vfail"]
    c.setFillColor(OK if verified else WARN)
    c.setFont("Helvetica-Bold", 10)
    sw = c.stringWidth(seal, "Helvetica-Bold", 10)
    c.drawString(W - doc.margin - sw, doc.h - 78, seal)
    scans = tr["scans"].format(n=passport.get("consumer_scans", 0))
    c.setFillColor(GOLD_SOFT)
    c.setFont("Helvetica", 9)
    sw2 = c.stringWidth(scans, "Helvetica", 9)
    c.drawString(W - doc.margin - sw2, doc.h - 94, scans)
    doc.y = doc.h - band_h - 6

    # ---- journey ----
    doc.heading(tr["journey"])
    doc.para(tr["journey_l"])
    doc.y -= 4
    for s in passport["stages"]:
        doc.ensure(30)
        doc.y -= 16
        name = STAGE.get(lang, {}).get(s["stage"], s["stage"])
        c.setFillColor(GOLD if s["event_type"] == "lab_verification" else LEAF)
        c.circle(doc.margin + 3, doc.y + 3, 3, fill=1, stroke=0)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(doc.margin + 14, doc.y, name)
        when = datetime.fromtimestamp(s["timestamp"], timezone.utc).strftime("%d %b %Y")
        c.setFillColor(INK_SOFT)
        c.setFont("Helvetica", 8)
        c.drawString(doc.margin + 14, doc.y - 11, f"{tr['by']} {s['by']} · {when} · {tr['signed']}")
        doc.y -= 11
        facts = [(k, v) for k, v in _facts(lang, s["event_type"], s.get("details", {}))
                 if v not in (None, "", [])]
        if facts:
            txt = "   ".join(f"{k}: {v}" for k, v in facts)
            doc.para(txt, color=INK, size=8.5, lead=11)

    # ---- by-products ----
    circ = passport.get("circular", [])
    if circ:
        doc.heading(tr["byp"])
        doc.para(tr["byp_l"])
        main = next((x for x in circ if x.get("mass_balance_ok")), circ[0])
        doc.ensure(24)
        doc.y -= 16
        rtype = main.get("residue_type") or "residue"
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(doc.margin, doc.y, tr["accounted"].format(
            kg=f"{main.get('generated_kg', 0):,}", type=rtype))
        c.setFillColor(GOLD if main.get("mass_balance_ok") else WARN)
        c.setFont("Helvetica-Bold", 11)
        pct = f"{main.get('recovery_pct', 0)}% {tr['recovered']}"
        c.drawRightString(W - doc.margin, doc.y, pct)
        doc.y -= 4
        outs = main.get("recovered_outputs", {}) or {}
        if outs:
            txt = "   ".join(f"{v:,} {OUT.get(lang, {}).get(k, k)}" for k, v in outs.items())
            doc.para(txt, color=INK_SOFT, size=9)
        for cc in circ:
            doc.ensure(14)
            doc.y -= 13
            status = tr["mb_ok"] if cc.get("mass_balance_ok") else tr["mb_wait"]
            c.setFillColor(INK)
            c.setFont("Helvetica", 9)
            c.drawString(doc.margin, doc.y,
                         f"{cc.get('generated_kg', 0):,} kg {cc.get('residue_type', '')}")
            c.setFillColor(OK if cc.get("mass_balance_ok") else WARN)
            c.drawRightString(W - doc.margin, doc.y, status)

    # ---- rewards ----
    rewards = passport.get("rewards", [])
    if rewards:
        agg = {}
        for r in rewards:
            k = (r["recipient"], r["for"])
            agg[k] = agg.get(k, 0) + r["amount"]
        doc.heading(tr["rec"])
        doc.para(tr["rec_l"])
        for (recipient, rule), amount in agg.items():
            doc.ensure(14)
            doc.y -= 13
            c.setFillColor(GOLD)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(doc.margin, doc.y, f"+{amount}")
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(doc.margin + 34, doc.y, recipient)
            c.setFillColor(INK_SOFT)
            c.setFont("Helvetica", 8.5)
            c.drawString(doc.margin + 34, doc.y - 10, WHY.get(lang, {}).get(rule, rule))
            doc.y -= 10

    # ---- verification block ----
    doc.ensure(180)
    doc.heading(tr["verify_h"])
    doc.para(tr["verify_l"])
    doc.y -= 8
    block_top = doc.y
    # QR on the right
    try:
        import qrcode
        qr_img = qrcode.make(verify_url, box_size=8, border=1)
        bio = io.BytesIO()
        qr_img.save(bio, format="PNG")
        bio.seek(0)
        qsz = 96
        c.drawImage(ImageReader(bio), W - doc.margin - qsz, block_top - qsz + 8,
                    qsz, qsz, preserveAspectRatio=True, mask="auto")
    except Exception:
        pass
    # details on the left
    def kv(label, value):
        doc.ensure(12)
        doc.y -= 12
        c.setFillColor(INK_SOFT)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(doc.margin, doc.y, label.upper())
        c.setFillColor(INK)
        c.setFont("Courier", 8)
        c.drawString(doc.margin + 92, doc.y, value)

    issued_str = datetime.fromtimestamp(issued_at, timezone.utc).strftime("%d %b %Y %H:%M UTC")
    kv(tr["issued"], issued_str)
    kv(tr["height"], str(height))
    kv(tr["head"], head_hash[:40] + "…")
    kv(tr["content"], attestation["content_sha256"][:40] + "…")
    kv(tr["issuer"], issuer_pub[:40] + "…")
    kv(tr["sig"], signature[:40] + "…")
    doc.y -= 14
    c.setFillColor(GREEN_MID)
    c.setFont("Helvetica", 8)
    for line in _wrap(c, verify_url, "Helvetica", 8, W - 2 * doc.margin):
        doc.ensure(11)
        doc.y -= 11
        c.drawString(doc.margin, doc.y, line)

    # ---- footer ----
    doc.y -= 10
    doc.para(tr["foot"], color=INK_SOFT, size=7.5, lead=10)

    c.showPage()
    c.save()
    return buf.getvalue(), {**attestation, "signature": signature, "issuer_public_key": issuer_pub}
