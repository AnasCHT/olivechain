"""Run the OliveChain API and web apps with local or Fabric persistence."""
import os

from olivechain import Registry, Ledger, EvidenceStore
from olivechain.oracle import WeatherOracle
from olivechain.api import create_app
from olivechain.crypto import KeyPair
from olivechain.models import Role
from olivechain.registry import PermissionError_

backend = os.environ.get("OLIVECHAIN_LEDGER_BACKEND", "local").strip().lower()
local_registry = Registry("data/registry.json")

if backend == "fabric":
    from olivechain.fabric_client import FabricAgentRouter
    from olivechain.fabric_registry import FabricRegistry
    from olivechain.fabric_ledger import FabricLedger

    router = FabricAgentRouter.from_env()
    registry = FabricRegistry(local_registry, router)
    ledger = FabricLedger(registry, router)
else:
    registry = local_registry
    ledger = Ledger(registry, "data/ledger.jsonl")

store = EvidenceStore("evidence_store")
weather_oracle = WeatherOracle(
    key_path=os.environ.get("OLIVECHAIN_WEATHER_ORACLE_KEY", "data/weather_oracle.key"),
    oracle_id=os.environ.get("OLIVECHAIN_WEATHER_ORACLE_ID", "olivechain-weather-oracle-machine1"),
)

# The public consumer portal keeps its browser/application Ed25519 identity.
# In Fabric mode, the event is additionally submitted by the consumer client
# certificate held by CourierOrg's local Gateway Agent.
_PORTAL_ID = "consumer-portal"
_KEY_PATH = "data/consumer_portal.key"
consumer_signer = None
try:
    registry.get(_PORTAL_ID)
    if os.path.exists(_KEY_PATH):
        with open(_KEY_PATH) as f:
            consumer_signer = (_PORTAL_ID, KeyPair.from_private_hex(f.read().strip()))
except PermissionError_:
    os.makedirs("data", exist_ok=True)
    kp = registry.register(_PORTAL_ID, "OliveChain Consumer Portal", [Role.CONSUMER])
    with open(_KEY_PATH, "w") as f:
        f.write(kp.private_hex)
    consumer_signer = (_PORTAL_ID, kp)

_ISSUER_KEY_PATH = "data/passport_issuer.key"
if os.path.exists(_ISSUER_KEY_PATH):
    with open(_ISSUER_KEY_PATH) as f:
        passport_signer = KeyPair.from_private_hex(f.read().strip())
else:
    os.makedirs("data", exist_ok=True)
    passport_signer = KeyPair.generate()
    with open(_ISSUER_KEY_PATH, "w") as f:
        f.write(passport_signer.private_hex)

app = create_app(
    registry,
    ledger,
    store,
    consumer_signer=consumer_signer,
    passport_signer=passport_signer,
    weather_oracle=weather_oracle,
)
