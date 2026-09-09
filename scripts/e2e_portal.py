"""Browser end-to-end test of the wallet portal's client-side signing.

Spins up a fresh server with an in-memory Fabric-compatible test adapter,
drives real Chromium through wallet creation -> login -> event submission,
then confirms over the API that the event actually committed to the ledger.
This is the only automated coverage of the browser WebCrypto signing path.

    python scripts/e2e_portal.py
"""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uvicorn

from olivechain import EvidenceStore, Ledger, Registry
from olivechain.api import create_app
from olivechain.crypto import KeyPair
from olivechain.models import EventType, Role

PORT = 8099
BASE = f"http://127.0.0.1:{PORT}"


class E2EFabricLedger:
    """Minimal Fabric-compatible adapter backed by the local audited ledger.

    The browser test exercises the production wallet/API/UI flow without
    requiring a four-organization Fabric network on a GitHub-hosted runner.
    Newly registered wallets receive an active farmer identity so the test can
    continue through an operational event submission.
    """

    backend_name = "fabric"

    def __init__(self, ledger, farmer_key):
        self.ledger = ledger
        self.farmer_key = farmer_key
        self._wallets = {}

    def __getattr__(self, name):
        return getattr(self.ledger, name)

    def register_wallet(self, wallet_address, public_key_spki, display_name):
        wallet = {
            "wallet_address": wallet_address,
            "public_key_spki": public_key_spki,
            "display_name": display_name,
            "status": "active",
            "role": "farmer",
            "role_status": "active",
            "org_id": "farmer-org",
            "org_name": "E2E Cooperative",
            "msp_id": "FarmerOrgMSP",
            "identity_alias": "user:e2e-farmer",
            "client_id_hash": "e2e-client-hash",
        }
        self._wallets[wallet_address] = wallet
        return dict(wallet)

    def get_wallet(self, wallet_address):
        return dict(self._wallets[wallet_address])

    def wallets(self):
        return [dict(wallet) for wallet in self._wallets.values()]

    def wallet_assets(self, _wallet_address):
        return {"eco_token": 0, "olive_token": 0, "trust_score": 50}

    def wallet_token_transactions(self, _wallet_address):
        return []

    def wallet_role_requests(self, _wallet_address):
        return []

    def token_policy(self):
        return {}

    def commit_prepared(self, body, _signature, **_kwargs):
        return self.ledger.append(
            EventType(body["event_type"]),
            body["subject_id"],
            body["actor_org"],
            body["payload"],
            self.farmer_key,
            evidence=body.get("evidence", []),
            timestamp=body.get("timestamp"),
        )


def build_app(tmp):
    registry = Registry(os.path.join(tmp, "registry.json"))
    farmer_key = registry.register("farmer-org", "E2E Cooperative", [Role.FARMER])
    local_ledger = Ledger(registry, os.path.join(tmp, "ledger.jsonl"))
    ledger = E2EFabricLedger(local_ledger, farmer_key)
    store = EvidenceStore(os.path.join(tmp, "evidence"))
    portal = registry.register("consumer-portal", "Portal", [Role.CONSUMER])
    return create_app(registry, ledger, store,
                      consumer_signer=("consumer-portal", portal),
                      passport_signer=KeyPair.generate())


def main():
    tmp = tempfile.mkdtemp(prefix="oc_e2e_")
    server = uvicorn.Server(uvicorn.Config(build_app(tmp), host="127.0.0.1",
                                           port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("server did not start")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{BASE}/portal", wait_until="networkidle")

        # --- Identity: create and authenticate a wallet in the browser ---
        page.wait_for_selector("#signupName")
        page.fill("#signupName", "E2E Cooperative")
        page.click("#createWalletBtn")
        page.wait_for_selector("#appScreen:not(.hidden)", timeout=12000)
        page.wait_for_selector("#submitTab:not(.hidden)")

        # --- Submit the first valid signed supply-chain event ---
        page.click("#submitTab")
        page.wait_for_selector("#view-submit.active")
        page.select_option("#eventType", "cultivation")
        page.fill("#subjectId", "BATCH-E2E-001")
        page.fill('[data-field="farm_id"]', "FARM-E2E")
        page.fill('[data-field="plot_id"]', "PLOT-E2E")
        page.fill('[data-field="cultivar"]', "Picholine Marocaine")
        page.fill('[data-field="practices"]', '{"irrigation":"drip"}')
        page.click("#submitBtn")

        try:
            page.wait_for_selector("#submitResult:not(.hidden)", timeout=12000)
        except Exception:
            err = page.inner_text("#submitErr") or "(no error text)"
            crypto_ok = page.evaluate("Boolean(window.isSecureContext && crypto?.subtle)")
            browser.close()
            print("FAIL: signing did not complete.")
            print("  portal error:", err)
            print("  WebCrypto P-256 available in this browser:", crypto_ok)
            if errors:
                print("  page errors:", errors)
            sys.exit(1)

        result = page.inner_text("#submitResult")
        browser.close()

    assert "committed" in result.lower(), result

    # --- Confirm the event really landed on the ledger, via the API ---
    events = json.loads(urllib.request.urlopen(
        f"{BASE}/events?subject=BATCH-E2E-001").read())
    cultivation = [e for e in events["events"]
                   if e["event_type"] == "cultivation"
                   and e["actor_org"] == "farmer-org"]
    assert cultivation, "cultivation event not found on the ledger"
    assert cultivation[0]["payload"]["farm_id"] == "FARM-E2E"

    audit = json.loads(urllib.request.urlopen(f"{BASE}/audit").read())
    assert audit["chain_valid"], audit["problems"]

    server.should_exit = True
    print("PASS: registered in-browser, signed with WebCrypto P-256, committed")
    print(f"  event {cultivation[0]['event_id']} on a valid chain (height {events['total']})")


if __name__ == "__main__":
    main()
