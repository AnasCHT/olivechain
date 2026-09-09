from fastapi.testclient import TestClient

from olivechain.api import create_app
from olivechain.crypto import KeyPair
from olivechain.evidence import EvidenceStore
from olivechain.ledger import GENESIS_HASH
from olivechain.models import Role
from olivechain.registry import Registry
from olivechain.wallet_auth import WalletAuth


class FakeRouter:
    def __init__(self):
        self.created = []
        self.status = []

    def health_for_org(self, org_id):
        return {"status": "ok", "org_id": org_id}

    def create_identity(self, org_id, username, display_name, role, wallet_address=""):
        self.created.append((org_id, username, display_name, role, wallet_address))
        return {
            "identity_alias": f"user:{username}",
            "client_id_hash": f"hash-{username}",
            "wallet_address": wallet_address,
        }

    def set_identity_status(self, org_id, identity_alias, active):
        self.status.append((org_id, identity_alias, active))
        return {"identity_alias": identity_alias, "active": active}


class FakeFabricLedger:
    backend_name = "fabric"
    head_hash = GENESIS_HASH

    def __init__(self):
        self.router = FakeRouter()
        self._wallets = {}
        self.grants = []

    def all(self):
        return []

    def verify_chain(self):
        return True, []

    def iter_type(self, _event_type):
        return iter(())

    def get_wallet(self, address):
        return dict(self._wallets[address])

    def wallets(self):
        return [dict(v) for v in self._wallets.values()]

    def role_requests_for_org(self, _org_id):
        return []

    def wallet_assets(self, _address):
        return {"eco_token": 0, "olive_token": 0, "trust_score": 50}

    def wallet_token_transactions(self, _address):
        return []

    def wallet_role_requests(self, _address):
        return []

    def token_policy(self):
        return {}

    def grant_wallet_role(self, org_id, admin_identity, wallet_address, role, client_id_hash, identity_alias):
        self.grants.append((org_id, admin_identity, wallet_address, role, client_id_hash, identity_alias))
        wallet = self._wallets[wallet_address]
        wallet.update({
            "org_id": org_id,
            "msp_id": "MakerOrgMSP" if org_id == "maker-org" else "FarmerOrgMSP",
            "role": role,
            "role_status": "active",
            "client_id_hash": client_id_hash,
            "identity_alias": identity_alias,
        })
        return dict(wallet)


def _registry(tmp_path):
    registry = Registry(str(tmp_path / "registry.json"))
    registry.register("farmer-org", "Farmer Cooperative", [Role.FARMER])
    registry.register("maker-org", "Olive Mill", [Role.MILL, Role.LABORATORY, Role.BOTTLER])
    return registry


def _wallet(address, name, **updates):
    value = {
        "wallet_address": address,
        "public_key_spki": "unused-in-this-test",
        "display_name": name,
        "status": "active",
        "role": "consumer",
        "role_status": "consumer",
        "org_id": "",
        "msp_id": "",
        "identity_alias": "",
        "client_id_hash": "",
    }
    value.update(updates)
    return value


def test_public_signup_hides_restricted_roles(tmp_path):
    ledger = FakeFabricLedger()
    auth = WalletAuth(secret_path=tmp_path / "wallet-secret")
    client = TestClient(create_app(
        _registry(tmp_path), ledger, EvidenceStore(str(tmp_path / "evidence")),
        passport_signer=KeyPair.generate(), wallet_auth=auth,
    ))
    response = client.get("/portal/auth/options")
    assert response.status_code == 200
    public = {row["role"] for row in response.json()["public_signup_roles"]}
    assert {"farmer", "collector", "distributor", "retailer"} <= public
    assert "laboratory" not in public
    assert "mill" not in public
    assert "bottler" not in public
    assert "processor" not in public
    assert "orgadmin" not in public


def test_password_login_is_removed(tmp_path):
    ledger = FakeFabricLedger()
    auth = WalletAuth(secret_path=tmp_path / "wallet-secret")
    client = TestClient(create_app(
        _registry(tmp_path), ledger, EvidenceStore(str(tmp_path / "evidence")),
        passport_signer=KeyPair.generate(), wallet_auth=auth,
    ))
    response = client.post("/portal/auth/login", json={"username": "x", "password": "y"})
    assert response.status_code == 410


def test_orgadmin_wallet_grants_restricted_role_to_existing_wallet(tmp_path):
    ledger = FakeFabricLedger()
    auth = WalletAuth(secret_path=tmp_path / "wallet-secret")
    admin = "OLIVE-AAAAAAAAAAAAAAAAAAAAAAAA"
    target = "OLIVE-BBBBBBBBBBBBBBBBBBBBBBBB"
    ledger._wallets[admin] = _wallet(
        admin, "Maker Administrator", org_id="maker-org", msp_id="MakerOrgMSP",
        role="orgadmin", role_status="active", identity_alias="user:w-admin",
        client_id_hash="hash-admin",
    )
    ledger._wallets[target] = _wallet(target, "Lab Operator")

    client = TestClient(create_app(
        _registry(tmp_path), ledger, EvidenceStore(str(tmp_path / "evidence")),
        passport_signer=KeyPair.generate(), wallet_auth=auth,
    ))
    token, session = auth.create_session(ledger._wallets[admin])
    client.cookies.set(auth.cookie_name, token)

    response = client.post(
        "/portal/admin/grants",
        headers={"X-CSRF-Token": session.csrf_token},
        json={"wallet_address": target, "role": "laboratory"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "laboratory"
    assert ledger.router.created[0][0] == "maker-org"
    assert ledger.router.created[0][3] == "laboratory"
    assert ledger.router.created[0][4] == target
    assert ledger.grants[0][0] == "maker-org"
