"""Integration and application layers for OliveChain.

The legacy local backend retains browser Ed25519 signing. In Fabric mode, the
new actor portal uses application sessions and routes each transaction to the
organization Gateway Agent holding the relevant MSP client identity. Fabric
private keys never enter the browser or the FastAPI process.
"""
import base64
import json
import os
import re
import secrets
import threading
import time
import uuid

from urllib.parse import quote

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from .crypto import canonical_json, sha256_hex, verify_signature
from .evidence import EvidenceStore
from .incentives import IncentiveEngine, due_rewards
from .ledger import Event, Ledger, LedgerError, GENESIS_HASH
from .massbalance import reconcile_residue
from .oracle import OracleError, WeatherOracle
from .models import EventType, PERMISSIONS, REQUIRED_FIELDS, Role
from .passport import build_passport
from .workflow import derive_status, statuses_from_events, transition_allowed
from .wallet_auth import (
    WalletAuth, WalletAuthError, WalletSession, PUBLIC_REQUEST_ROLES,
    RESTRICTED_ROLES, ORG_NAMES,
)
from .registry import PermissionError_, Registry
from . import anomaly


class PrepareEvent(BaseModel):
    event_type: str
    subject_id: str
    actor_org: str
    payload: dict
    evidence: list[dict] = []


class CommitEvent(BaseModel):
    body: dict          # exact body returned by /events/prepare
    signature: str      # hex Ed25519 by actor_org over canonical_json(body)


class RegisterOrg(BaseModel):
    org_id: str
    name: str
    roles: list[str]
    onboard_code: str | None = None


class WalletRegister(BaseModel):
    wallet_address: str
    public_key_spki: str
    display_name: str
    signature: str


class WalletRegisterChallenge(BaseModel):
    wallet_address: str
    public_key_spki: str


class WalletChallenge(BaseModel):
    wallet_address: str


class WalletLogin(BaseModel):
    wallet_address: str
    signature: str


class WalletRoleRequestInput(BaseModel):
    role: str


class WalletAdminGrant(BaseModel):
    wallet_address: str
    role: str


class WalletAdminDecision(BaseModel):
    reason: str = ""


class WalletRevoke(BaseModel):
    reason: str = ""


class PortalSubmitEvent(BaseModel):
    event_type: str
    subject_id: str
    payload: dict
    evidence: list[dict] = []


class EvidenceUpload(BaseModel):
    name: str
    content_base64: str


class WeatherOracleRequest(BaseModel):
    latitude: float
    longitude: float
    accuracy_m: float | None = None
    event_type: str
    subject_id: str


class VerifyAttestation(BaseModel):
    batch_id: str
    content_sha256: str
    ledger_head_hash: str
    ledger_height: int
    ledger_verified: bool
    issued_at: int
    signature: str
    type: str = "olivechain-passport-attestation"
    version: int = 1


FRONTEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

# Set OLIVECHAIN_ONBOARD_CODE to require an invite code for org registration.
ONBOARD_CODE = os.environ.get("OLIVECHAIN_ONBOARD_CODE") or None

# GS1 Digital Link GTIN. A real GTIN must be assigned by GS1; this placeholder
# lets the standard link/resolver work end-to-end in the pilot. When the env
# var is set, QR codes use the GS1 Digital Link form instead of a plain URL.
GTIN = os.environ.get("OLIVECHAIN_GTIN") or "09506000134352"
GS1_CONFIGURED = bool(os.environ.get("OLIVECHAIN_GTIN"))

# Operator authentication. When both are set, every surface except the
# consumer-public allowlist below requires HTTP Basic auth. Left unset, the
# server runs open (dev/demo) — create_app warns at startup.
ADMIN_USER = os.environ.get("OLIVECHAIN_ADMIN_USER") or None
ADMIN_PASS = os.environ.get("OLIVECHAIN_ADMIN_PASSWORD") or None

# Surfaces consumers and their apps must reach without credentials.
PUBLIC_EXACT = {
    "/verify", "/m", "/portal", "/i18n.js", "/manifest.webmanifest", "/sw.js", "/icon.svg",
    "/favicon.ico", "/health", "/stats", "/subjects", "/docs", "/openapi.json",
    "/redoc", "/passport/issuer", "/passport/verify", "/credentials/verify",
}
PUBLIC_PREFIX = ("/passport-view/", "/passport/", "/qr/", "/labels/", "/scan/", "/01/", "/portal/auth/", "/portal/wallet/register", "/portal/wallet/challenge", "/portal/wallet/login")


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIX)


def _basic_ok(header: str | None) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except Exception:
        return False
    return (secrets.compare_digest(user, ADMIN_USER or "")
            and secrets.compare_digest(pw, ADMIN_PASS or ""))

MAX_PAYLOAD_BYTES = 32 * 1024
MAX_EVIDENCE_REFS = 10
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]")

# The exact signing-body keys; commit rejects anything else.
_BODY_KEYS = {"event_id", "event_type", "subject_id", "actor_org",
              "timestamp", "payload", "evidence", "prev_hash"}

_CSP = "; ".join([
    "default-src 'self'",
    # inline scripts are part of the self-contained pages; Swagger UI loads from jsdelivr
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net",
    "font-src https://fonts.gstatic.com",
    "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.jsdelivr.net",
    "connect-src 'self'",
    "manifest-src 'self'",
    "frame-ancestors 'self'",
])


class RateLimiter:
    """Small in-memory sliding-window limiter, keyed per client + action.
    Behind a reverse proxy, make sure client IPs are restored (e.g.
    uvicorn --proxy-headers) or all clients share one bucket."""

    def __init__(self):
        self._hits: dict[tuple, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: tuple, limit: int, window_s: float) -> bool:
        now = time.time()
        with self._lock:
            q = self._hits.setdefault(key, [])
            while q and q[0] <= now - window_s:
                q.pop(0)
            if len(q) >= limit:
                return False
            q.append(now)
            return True

# Loop-1 event types identify batch subjects; loop-2 types identify residue lots.
_BATCH_TYPES = {EventType.CULTIVATION.value, EventType.HARVEST.value,
                EventType.COLLECTION_TRANSPORT.value, EventType.MILLING.value,
                EventType.LAB_VERIFICATION.value, EventType.BOTTLING.value,
                EventType.DISTRIBUTION_RETAIL.value, EventType.CONSUMER_VERIFICATION.value}
_RESIDUE_TYPES = {EventType.RESIDUE_GENERATION.value, EventType.RESIDUE_CUSTODY.value,
                  EventType.VALORIZATION.value, EventType.USEFUL_OUTPUT.value,
                  EventType.RETURN_OR_SALE.value, EventType.ENV_ACCOUNTING.value}


def create_app(registry: Registry, ledger: Ledger, evidence: EvidenceStore,
               engine: IncentiveEngine | None = None,
               consumer_signer: tuple | None = None,
               passport_signer=None,
               wallet_auth: WalletAuth | None = None,
               weather_oracle: WeatherOracle | None = None) -> FastAPI:
    app = FastAPI(title="OliveChain", version="1.0.0",
                  description="Wallet-authenticated circular trust system for olive oil")
    wallet_auth = wallet_auth or WalletAuth(
        secret_path=os.environ.get("OLIVECHAIN_WALLET_SESSION_SECRET_FILE", "data/wallet_session_secret"),
    )

    write_lock = threading.Lock()   # serializes every ledger/registry mutation
    limiter = RateLimiter()
    started = time.time()

    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Content-Security-Policy", _CSP)
        return resp

    @app.middleware("http")
    async def gate_and_headers(request: Request, call_next):
        # Operator gate: when credentials are configured, everything outside
        # the consumer-public allowlist requires HTTP Basic auth.
        if ADMIN_USER and ADMIN_PASS and not _is_public_path(request.url.path):
            if not _basic_ok(request.headers.get("Authorization")):
                return _headers(Response(status_code=401, headers={
                    "WWW-Authenticate": 'Basic realm="OliveChain operators"'}))
        return _headers(await call_next(request))

    if not (ADMIN_USER and ADMIN_PASS):
        import sys
        print("WARNING: OLIVECHAIN_ADMIN_USER/PASSWORD unset — operator surfaces "
              "(dashboard, portal, governance, admin) are open. Set both to require "
              "authentication.", file=sys.stderr)

    def _limit(request: Request, action: str, limit: int, window_s: float):
        ip = request.client.host if request.client else "unknown"
        if not limiter.allow((ip, action), limit, window_s):
            raise HTTPException(429, f"rate limit exceeded for {action}; retry later")

    def _org_name(org_id: str) -> str:
        try:
            return registry.get(org_id).name
        except PermissionError_:
            return org_id

    def _workflow_status(subject_id: str) -> dict:
        method = getattr(ledger, "workflow_status", None)
        if callable(method):
            return method(subject_id)
        return derive_status(
            subject_id, ledger.for_subject(subject_id, include_superseded=False)
        ).to_dict()

    def _workflow_statuses() -> list[dict]:
        method = getattr(ledger, "workflow_statuses", None)
        if callable(method):
            return list(method())
        return statuses_from_events(ledger.all())

    def _wallet_lookup(address: str) -> dict:
        if getattr(ledger, "backend_name", "local") != "fabric":
            raise WalletAuthError("wallet authentication requires the Fabric backend")
        try:
            return ledger.get_wallet(address)
        except Exception as exc:
            raise WalletAuthError(str(exc)) from exc

    def _portal_session(request: Request, require_csrf: bool = False) -> WalletSession:
        session = wallet_auth.parse_session(
            request.cookies.get(wallet_auth.cookie_name), _wallet_lookup
        )
        if session is None:
            raise HTTPException(401, "wallet authentication required")
        if require_csrf and not wallet_auth.validate_csrf(
                session, request.headers.get("X-CSRF-Token")):
            raise HTTPException(403, "invalid CSRF token")
        return session

    def _set_portal_cookie(response: Response, token: str) -> None:
        response.set_cookie(
            wallet_auth.cookie_name, token,
            max_age=wallet_auth.session_ttl_seconds,
            httponly=True, secure=wallet_auth.cookie_secure,
            samesite="strict", path="/",
        )

    # ---------------------------------------------------------------- web app
    @app.get("/", include_in_schema=False)
    def root():
        index = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.isfile(index):
            return FileResponse(index, media_type="text/html")
        return RedirectResponse("/docs")

    @app.get("/passport-view/{batch_id}", include_in_schema=False)
    def passport_view(batch_id: str):
        page = os.path.join(FRONTEND_DIR, "passport.html")
        if os.path.isfile(page):
            return FileResponse(page, media_type="text/html")
        raise HTTPException(404, "passport page not installed")

    @app.get("/verify", include_in_schema=False)
    def verify_page():
        page = os.path.join(FRONTEND_DIR, "customer.html")
        if os.path.isfile(page):
            return FileResponse(page, media_type="text/html")
        raise HTTPException(404, "consumer app not installed")

    def _frontend_file(name: str, media_type: str):
        path = os.path.join(FRONTEND_DIR, name)
        if os.path.isfile(path):
            return FileResponse(path, media_type=media_type)
        raise HTTPException(404, f"{name} not installed")

    @app.get("/m", include_in_schema=False)
    def mobile_app():
        return _frontend_file("mobile.html", "text/html")

    @app.get("/portal", include_in_schema=False)
    def actor_portal():
        return _frontend_file("portal.html", "text/html")

    @app.get("/labels/{batch_id}", include_in_schema=False)
    def label_sheet(batch_id: str):
        return _frontend_file("labels.html", "text/html")

    def _batch_exists(batch_id: str) -> bool:
        return any(e.subject_id == batch_id and e.event_type in _BATCH_TYPES
                   for e in ledger.all())

    @app.get("/qr/{batch_id}.svg")
    def qr_svg(batch_id: str, request: Request):
        """QR code for a bottle label: deep-links to the mobile verifier with
        the batch pre-filled. SVG, so it prints crisply at any size."""
        if not _batch_exists(batch_id):
            raise HTTPException(404, f"unknown batch {batch_id}")
        import io
        import qrcode
        import qrcode.image.svg
        base = str(request.base_url).rstrip("/")
        if GS1_CONFIGURED:
            from .credentials import gs1_digital_link
            url = gs1_digital_link(base, GTIN, batch_id)
        else:
            url = base + "/m?batch=" + quote(batch_id, safe="")
        img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage,
                          box_size=10, border=2)
        buf = io.BytesIO()
        img.save(buf)
        return Response(buf.getvalue(), media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return _frontend_file("manifest.webmanifest", "application/manifest+json")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        return _frontend_file("sw.js", "text/javascript")

    @app.get("/i18n.js", include_in_schema=False)
    def i18n_js():
        return _frontend_file("i18n.js", "text/javascript")

    @app.get("/icon.svg", include_in_schema=False)
    def app_icon():
        return _frontend_file("icon.svg", "image/svg+xml")

    @app.post("/scan/{batch_id}")
    def scan_batch(batch_id: str, request: Request):
        """Record a consumer verification scan as a real signed ledger event,
        submitted by the consumer portal organization on the scanner's behalf."""
        _limit(request, "scan", 10, 60)
        if consumer_signer is None:
            raise HTTPException(503, "consumer portal signer not configured")
        if not any(e.subject_id == batch_id and e.event_type in _BATCH_TYPES
                   for e in ledger.all()):
            raise HTTPException(404, f"unknown batch {batch_id}")
        org_id, key = consumer_signer
        with write_lock:
            ev = ledger.append(EventType.CONSUMER_VERIFICATION, batch_id, org_id,
                               {"channel": "web_portal"}, key)
        scans = sum(1 for e in ledger.iter_type(EventType.CONSUMER_VERIFICATION)
                    if e.subject_id == batch_id)
        return {"recorded": True, "event_id": ev.event_id, "consumer_scans": scans}

    # ---------------------------------------------------------------- read API
    @app.get("/health")
    def health(deep: bool = False):
        """Liveness probe. With deep=true also re-verifies the full chain."""
        out = {"status": "ok", "height": len(ledger),
               "ledger_backend": getattr(ledger, "backend_name", "local"),
               "uptime_s": round(time.time() - started, 1)}
        if deep:
            ok, problems = ledger.verify_chain()
            out["chain_valid"] = ok
            if not ok:
                out["status"] = "degraded"
                out["problems"] = problems[:5]
        return out

    @app.get("/stats")
    def stats():
        evs = ledger.all()
        chain_ok, problems = ledger.verify_chain()
        by_type: dict[str, int] = {}
        eco_points = 0
        for e in evs:
            by_type[e.event_type] = by_type.get(e.event_type, 0) + 1
            if e.event_type == EventType.REWARD_ISSUED.value and e.superseded_by is None:
                eco_points += int(e.payload.get("amount", 0))
        flags = {e.payload["subject_event"]: e.event_id
                 for e in ledger.iter_type(EventType.REVIEW_FLAG)}
        resolved = {e.payload["flag_event"]
                    for e in ledger.iter_type(EventType.REVIEW_RESOLUTION)}
        return {
            "height": len(evs),
            "head_hash": evs[-1].event_hash if evs else GENESIS_HASH,
            "chain_valid": chain_ok,
            "problems": problems,
            "organizations": len(registry.all()),
            "eco_points_issued": eco_points,
            "consumer_scans": by_type.get(EventType.CONSUMER_VERIFICATION.value, 0),
            "open_flags": sum(1 for fid in flags.values() if fid not in resolved),
            "events_by_type": by_type,
            "ledger_backend": getattr(ledger, "backend_name", "local"),
        }

    @app.get("/admin/export")
    def admin_export():
        """Download a full backup — ledger, registry and off-chain evidence —
        as a checksummed gzipped tar. Requires operator credentials to be
        configured, and (when configured) valid ones. Restore with
        scripts/restore.py."""
        if not (ADMIN_USER and ADMIN_PASS):
            raise HTTPException(503, "operator credentials not configured; refusing to export")
        from .backup import make_backup
        with write_lock:
            ok, _ = ledger.verify_chain()
            evs = ledger.all()
            summary = {"height": len(evs),
                       "head_hash": evs[-1].event_hash if evs else GENESIS_HASH,
                       "chain_valid": ok}
            data = make_backup(getattr(registry, "path", None),
                               getattr(ledger, "path", None),
                               getattr(evidence, "root", None), extra=summary)
        ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        return Response(data, media_type="application/gzip", headers={
            "Content-Disposition": f'attachment; filename="olivechain-backup-{ts}.tar.gz"'})

    @app.get("/subjects")
    def subjects():
        batches: list[str] = []
        residues: list[str] = []
        for e in ledger.all():
            if e.event_type in _BATCH_TYPES and e.subject_id not in batches:
                batches.append(e.subject_id)
            elif e.event_type in _RESIDUE_TYPES and e.subject_id not in residues:
                residues.append(e.subject_id)
        return {"batches": batches, "residues": residues}

    @app.get("/events")
    def events(limit: int = 50, offset: int = 0,
               event_type: str | None = None, subject: str | None = None):
        evs = ledger.all()
        if event_type:
            evs = [e for e in evs if e.event_type == event_type]
        if subject:
            q = subject.lower()
            evs = [e for e in evs if q in e.subject_id.lower() or q in e.actor_org.lower()]
        total = len(evs)
        page = list(reversed(evs))[offset:offset + limit]  # newest first
        return {"total": total, "events": [{
            "event_id": e.event_id,
            "event_type": e.event_type,
            "subject_id": e.subject_id,
            "actor_org": e.actor_org,
            "actor_name": _org_name(e.actor_org),
            "actor_user": getattr(e, "actor_user", ""),
            "actor_wallet": getattr(e, "actor_wallet", ""),
            "timestamp": e.timestamp,
            "payload": e.payload,
            "evidence": e.evidence,
            "event_hash": e.event_hash,
            "superseded_by": e.superseded_by,
        } for e in page]}

    # ----------------------------------------------- Wallet authentication
    @app.get("/portal/auth/options")
    def portal_auth_options():
        organizations = []
        for org_id, name in ORG_NAMES.items():
            organizations.append({
                "org_id": org_id,
                "name": name,
                "public_signup_roles": [
                    role for role, spec in PUBLIC_REQUEST_ROLES.items()
                    if spec["org_id"] == org_id
                ],
                "restricted_roles": RESTRICTED_ROLES.get(org_id, []),
            })
        return {
            "organizations": organizations,
            "public_signup_roles": [
                {"role": role, **spec} for role, spec in PUBLIC_REQUEST_ROLES.items()
            ],
            "default_role": "consumer",
        }

    @app.post("/portal/wallet/register-challenge")
    def wallet_register_challenge(req: WalletRegisterChallenge, request: Request):
        _limit(request, "wallet-register-challenge", 12, 3600)
        try:
            address = wallet_auth.validate_address(req.wallet_address)
            if wallet_auth.expected_address(req.public_key_spki) != address:
                raise WalletAuthError("wallet address does not match the public key")
            try:
                existing = ledger.get_wallet(address)
            except Exception:
                existing = None
            if existing:
                raise WalletAuthError("wallet is already registered")
            return wallet_auth.issue_challenge(address, purpose="register")
        except WalletAuthError as exc:
            status = 409 if "already registered" in str(exc).lower() else 422
            raise HTTPException(status, str(exc))

    @app.post("/portal/wallet/register")
    def wallet_register(req: WalletRegister, request: Request):
        _limit(request, "wallet-register", 8, 3600)
        if getattr(ledger, "backend_name", "local") != "fabric":
            raise HTTPException(409, "wallet registration requires the Fabric backend")
        try:
            address = wallet_auth.validate_address(req.wallet_address)
            if wallet_auth.expected_address(req.public_key_spki) != address:
                raise WalletAuthError("wallet address does not match the public key")
            wallet_auth.verify_challenge(
                address, req.public_key_spki, req.signature, purpose="register"
            )
            name = req.display_name.strip()
            if not name or len(name) > 120:
                raise WalletAuthError("display_name is required (max 120 characters)")
            return ledger.register_wallet(address, req.public_key_spki, name)
        except Exception as exc:
            # Fabric errors are intentionally returned without private agent details.
            message = str(exc)
            status = 409 if "already registered" in message.lower() else 422
            raise HTTPException(status, message)

    @app.post("/portal/wallet/challenge")
    def wallet_challenge(req: WalletChallenge, request: Request):
        _limit(request, "wallet-challenge", 30, 300)
        try:
            wallet = _wallet_lookup(wallet_auth.validate_address(req.wallet_address))
            if wallet.get("status") != "active":
                raise WalletAuthError("wallet is disabled")
            return wallet_auth.issue_challenge(wallet["wallet_address"], purpose="login")
        except WalletAuthError as exc:
            raise HTTPException(404, str(exc))

    @app.post("/portal/wallet/login")
    def wallet_login(req: WalletLogin, request: Request):
        _limit(request, "wallet-login", 15, 300)
        try:
            address = wallet_auth.validate_address(req.wallet_address)
            wallet = _wallet_lookup(address)
            wallet_auth.verify_challenge(address, wallet["public_key_spki"], req.signature, purpose="login")
            token, session = wallet_auth.create_session(wallet)
        except WalletAuthError as exc:
            raise HTTPException(401, str(exc))
        response = JSONResponse(session.public_dict())
        _set_portal_cookie(response, token)
        return response

    @app.post("/portal/auth/login")
    def password_login_removed():
        raise HTTPException(410, "password login was removed; connect an OliveChain wallet")

    @app.get("/portal/auth/session")
    def portal_session(request: Request):
        session = wallet_auth.parse_session(
            request.cookies.get(wallet_auth.cookie_name), _wallet_lookup
        )
        return session.public_dict() if session is not None else {"authenticated": False}

    @app.post("/portal/auth/logout")
    def portal_logout(request: Request):
        _portal_session(request, require_csrf=True)
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(wallet_auth.cookie_name, path="/")
        return response

    @app.get("/portal/wallet/me")
    def wallet_me(request: Request):
        session = _portal_session(request)
        wallet = _wallet_lookup(session.wallet_address)
        return {
            "wallet": wallet,
            "assets": ledger.wallet_assets(session.wallet_address),
            "transactions": ledger.wallet_token_transactions(session.wallet_address),
            "role_requests": ledger.wallet_role_requests(session.wallet_address),
            "token_policy": ledger.token_policy(),
        }

    @app.post("/portal/wallet/role-request")
    def wallet_role_request(req: WalletRoleRequestInput, request: Request):
        session = _portal_session(request, require_csrf=True)
        if req.role not in PUBLIC_REQUEST_ROLES:
            raise HTTPException(422, "this role is not available through public sign-up")
        try:
            return ledger.request_wallet_role(session.wallet_address, req.role)
        except Exception as exc:
            raise HTTPException(422, str(exc))

    @app.get("/portal/workflow/statuses")
    def portal_workflow_statuses(request: Request):
        _portal_session(request)
        statuses = _workflow_statuses()
        return {
            "batches": [row for row in statuses if row.get("workflow") == "product"],
            "residues": [row for row in statuses if row.get("workflow") == "circular"],
        }

    @app.get("/portal/workflow/status/{subject_id}")
    def portal_workflow_status(subject_id: str, request: Request):
        _portal_session(request)
        return _workflow_status(subject_id)

    @app.get("/portal/agent-health")
    def portal_agent_health(request: Request):
        session = _portal_session(request)
        router = getattr(ledger, "router", None)
        if router is None:
            raise HTTPException(409, "Fabric Gateway routing is unavailable")
        try:
            return router.health_for_org(session.org_id)
        except Exception as exc:
            raise HTTPException(503, f"Gateway Agent unavailable: {exc}")

    def _require_orgadmin(request: Request, *, csrf: bool = False) -> WalletSession:
        session = _portal_session(request, require_csrf=csrf)
        if session.role != "orgadmin" or not session.operational:
            raise HTTPException(403, "organization administrator wallet required")
        return session

    def _wallet_identity_username(wallet_address: str) -> str:
        return "w-" + wallet_address.split("-", 1)[1].lower()[:20]

    def _issue_fabric_identity(org_id: str, wallet: dict, role: str) -> dict:
        router = getattr(ledger, "router", None)
        if router is None:
            raise WalletAuthError("Fabric Gateway routing is unavailable")
        return router.create_identity(
            org_id,
            _wallet_identity_username(wallet["wallet_address"]),
            wallet.get("display_name") or wallet["wallet_address"],
            role,
            wallet_address=wallet["wallet_address"],
        )

    @app.get("/portal/admin/role-requests")
    def admin_role_requests(request: Request):
        session = _require_orgadmin(request)
        return {
            "organization": {"org_id": session.org_id, "name": session.org_name, "msp_id": session.msp_id},
            "requests": ledger.role_requests_for_org(session.org_id),
            "restricted_roles": RESTRICTED_ROLES.get(session.org_id, []),
        }

    @app.get("/portal/admin/wallets")
    def admin_wallets(request: Request):
        session = _require_orgadmin(request)
        rows = ledger.wallets()
        return {"wallets": [row for row in rows if not row.get("org_id") or row.get("org_id") == session.org_id]}

    @app.post("/portal/admin/role-requests/{request_id}/approve")
    def admin_approve_role_request(request_id: str, request: Request):
        session = _require_orgadmin(request, csrf=True)
        role_request = ledger.get_role_request(request_id)
        if role_request.get("requested_org_id") != session.org_id:
            raise HTTPException(403, "role request belongs to another organization")
        wallet = _wallet_lookup(role_request["wallet_address"])
        created = None
        try:
            created = _issue_fabric_identity(session.org_id, wallet, role_request["requested_role"])
            return ledger.approve_wallet_role(
                session.org_id, session.identity_alias, request_id,
                created.get("client_id_hash", ""), created["identity_alias"],
            )
        except Exception as exc:
            if created:
                try:
                    ledger.router.set_identity_status(session.org_id, created["identity_alias"], False)
                except Exception:
                    pass
            raise HTTPException(422, str(exc))

    @app.post("/portal/admin/role-requests/{request_id}/reject")
    def admin_reject_role_request(request_id: str, req: WalletAdminDecision, request: Request):
        session = _require_orgadmin(request, csrf=True)
        try:
            return ledger.reject_wallet_role(session.org_id, session.identity_alias, request_id, req.reason)
        except Exception as exc:
            raise HTTPException(422, str(exc))

    @app.post("/portal/admin/grants")
    def admin_grant_restricted_role(req: WalletAdminGrant, request: Request):
        session = _require_orgadmin(request, csrf=True)
        allowed = set(RESTRICTED_ROLES.get(session.org_id, []))
        if req.role not in allowed:
            raise HTTPException(422, "role is not a restricted role grantable by this organization")
        wallet = _wallet_lookup(req.wallet_address)
        created = None
        try:
            created = _issue_fabric_identity(session.org_id, wallet, req.role)
            return ledger.grant_wallet_role(
                session.org_id, session.identity_alias, wallet["wallet_address"], req.role,
                created.get("client_id_hash", ""), created["identity_alias"],
            )
        except Exception as exc:
            if created:
                try:
                    ledger.router.set_identity_status(session.org_id, created["identity_alias"], False)
                except Exception:
                    pass
            raise HTTPException(422, str(exc))

    @app.post("/portal/admin/wallets/{wallet_address}/revoke")
    def admin_revoke_wallet_role(wallet_address: str, req: WalletRevoke, request: Request):
        session = _require_orgadmin(request, csrf=True)
        wallet = _wallet_lookup(wallet_address)
        if wallet.get("org_id") != session.org_id:
            raise HTTPException(403, "wallet role belongs to another organization")
        try:
            if wallet.get("identity_alias", "").startswith("user:"):
                ledger.router.set_identity_status(session.org_id, wallet["identity_alias"], False)
            return ledger.revoke_wallet_role(
                session.org_id, session.identity_alias, wallet["wallet_address"], req.reason
            )
        except Exception as exc:
            raise HTTPException(422, str(exc))

    @app.get("/portal/oracle/info")
    def portal_oracle_info(request: Request):
        _portal_session(request)
        if weather_oracle is None:
            raise HTTPException(503, "external-data oracle is not configured")
        return {
            "oracle_id": weather_oracle.oracle_id,
            "provider": "open-meteo",
            "public_key": weather_oracle.public_key_hex,
            "mode": "ambient weather and air quality",
            "warning": (
                "Ambient weather is not a substitute for truck, tank, storage, "
                "scale, or processing sensor measurements."
            ),
        }

    @app.post("/portal/oracle/weather")
    def portal_weather_oracle(req: WeatherOracleRequest, request: Request):
        session = _portal_session(request, require_csrf=True)
        _limit(request, "portal-weather-oracle", 30, 60)
        if weather_oracle is None:
            raise HTTPException(503, "external-data oracle is not configured")
        try:
            event_type = EventType(req.event_type)
            role = Role(session.role)
        except ValueError as exc:
            raise HTTPException(422, f"unknown event type or role: {exc}")
        if role not in PERMISSIONS[event_type]:
            raise HTTPException(
                403,
                f"role {role.value} may not submit {event_type.value}",
            )
        try:
            result = weather_oracle.fetch_current(
                latitude=req.latitude,
                longitude=req.longitude,
                accuracy_m=req.accuracy_m,
                event_type=event_type.value,
                subject_id=req.subject_id.strip(),
            )
        except OracleError as exc:
            raise HTTPException(502, str(exc))

        evidence_ref = evidence.put(
            f"oracle_{event_type.value}_{req.subject_id}_{int(time.time())}.json",
            result["raw_bytes"],
        )
        return {
            "external_conditions": result["attestation"],
            "evidence": evidence_ref,
            "summary": result["attestation"]["body"],
        }

    @app.post("/portal/evidence")
    def portal_upload_evidence(req: EvidenceUpload, request: Request):
        _portal_session(request, require_csrf=True)
        _limit(request, "portal-evidence", 20, 60)
        import base64 as _base64
        name = _SAFE_NAME.sub("_", os.path.basename(req.name)).strip(" .")
        if not name or len(name) > 100:
            raise HTTPException(400, "artifact name must be 1-100 safe characters")
        try:
            data = _base64.b64decode(req.content_base64, validate=True)
        except Exception:
            raise HTTPException(400, "content_base64 is not valid base64")
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(413, "evidence artifact larger than 5 MB")
        return evidence.put(name, data)

    @app.post("/portal/events/submit")
    def portal_submit_event(req: PortalSubmitEvent, request: Request):
        session = _portal_session(request, require_csrf=True)
        _limit(request, "portal-submit", 60, 60)
        if not session.operational or session.role in {"consumer", "orgadmin"}:
            raise HTTPException(403, "an active operational Fabric role is required to submit events")
        if getattr(ledger, "backend_name", "local") != "fabric":
            raise HTTPException(409, "the actor portal requires the Fabric backend")
        try:
            etype = EventType(req.event_type)
            role = Role(session.role)
        except ValueError as exc:
            raise HTTPException(400, f"unknown event type or role: {exc}")
        if role not in PERMISSIONS[etype]:
            raise HTTPException(403, f"role {role.value} may not submit {etype.value}")
        missing = [field for field in REQUIRED_FIELDS[etype] if field not in req.payload]
        if missing:
            raise HTTPException(422, f"missing fields: {missing}")
        if not req.subject_id.strip() or len(req.subject_id) > 160:
            raise HTTPException(422, "subject_id is required (max 160 characters)")
        if len(canonical_json(req.payload)) > MAX_PAYLOAD_BYTES:
            raise HTTPException(413, "payload too large")
        if len(req.evidence) > MAX_EVIDENCE_REFS or not all(
                isinstance(item, dict) and isinstance(item.get("name"), str)
                and isinstance(item.get("sha256"), str)
                and isinstance(item.get("uri"), str)
                for item in req.evidence):
            raise HTTPException(422, "malformed evidence references")
        if etype not in {EventType.CORRECTION, EventType.REWARD_ISSUED,
                         EventType.REVIEW_FLAG, EventType.REVIEW_RESOLUTION}:
            status = _workflow_status(req.subject_id.strip())
            allowed, reason = transition_allowed(status, etype.value)
            if not allowed:
                raise HTTPException(409, reason)
        body = {
            "event_id": str(uuid.uuid4()),
            "event_type": etype.value,
            "subject_id": req.subject_id.strip(),
            "actor_org": session.org_id,
            "timestamp": time.time(),
            "payload": req.payload,
            "evidence": req.evidence,
            "prev_hash": getattr(ledger, "head_hash", GENESIS_HASH),
        }
        try:
            with write_lock:
                try:
                    ev = ledger.commit_prepared(
                        body,
                        f"portal-session:{session.username}",
                        role_override=session.role,
                        identity_override=session.identity_alias,
                        portal_user={
                            "username": session.wallet_address,
                            "display_name": session.display_name,
                            "wallet_address": session.wallet_address,
                        },
                    )
                except TypeError as exc:
                    # Compatibility with test/local adapters that implement the
                    # older commit_prepared signature.
                    if "unexpected keyword argument" not in str(exc):
                        raise
                    ev = ledger.commit_prepared(
                        body,
                        f"portal-session:{session.username}",
                        role_override=session.role,
                    )
        except PermissionError_ as exc:
            raise HTTPException(403, str(exc))
        except LedgerError as exc:
            message = str(exc)
            status = 409 if any(word in message.lower() for word in ("already", "advanced", "workflow", "next allowed", "first required", "current step")) else 422
            raise HTTPException(status, message)
        return {
            "event_id": ev.event_id,
            "event_hash": ev.event_hash,
            "event_type": ev.event_type,
            "subject_id": ev.subject_id,
            "actor_org": session.org_id,
            "actor_user": session.wallet_address,
            "wallet_address": session.wallet_address,
            "role": session.role,
        }

    @app.get("/organizations")
    def organizations():
        return [{"org_id": o.org_id, "name": o.name,
                 "roles": [r.value for r in o.roles],
                 "public_key": o.public_key} for o in registry.all()]

    @app.post("/organizations/register")
    def register_org(req: RegisterOrg, request: Request):
        """Onboard a legacy local-backend organization. The keypair is generated here and the
        private key is returned ONCE — the registry keeps only the public key.
        Open by default for the pilot; set the OLIVECHAIN_ONBOARD_CODE
        environment variable to require an invite code."""
        _limit(request, "register", 5, 3600)
        if getattr(ledger, "backend_name", "local") == "fabric":
            raise HTTPException(409, "Fabric consortium organizations are managed through MSP and channel governance")
        if ONBOARD_CODE and req.onboard_code != ONBOARD_CODE:
            raise HTTPException(403, "a valid onboard_code is required to register")
        try:
            roles = [Role(r) for r in req.roles]
        except ValueError as e:
            raise HTTPException(400, f"unknown role: {e}")
        if not roles:
            raise HTTPException(400, "at least one role is required")
        org_id = req.org_id.strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", org_id):
            raise HTTPException(400, "org_id must be 2-64 chars: lowercase letters, digits, - or _")
        if not req.name.strip() or len(req.name) > 120:
            raise HTTPException(400, "name is required (max 120 chars)")
        try:
            with write_lock:
                kp = registry.register(org_id, req.name.strip(), roles)
        except ValueError as e:
            raise HTTPException(409, str(e))
        return {"org_id": org_id, "name": req.name.strip(),
                "roles": [r.value for r in roles],
                "public_key": kp.public_hex,
                "private_key": kp.private_hex,
                "warning": "Store the private key now; the server does not keep it."}

    @app.get("/schema")
    def schema():
        """Event catalogue: which roles may submit each type, and the
        required payload fields — drives the actor portal's dynamic forms."""
        return [{"event_type": et.value,
                 "allowed_roles": sorted(r.value for r in PERMISSIONS[et]),
                 "required_fields": REQUIRED_FIELDS[et]} for et in EventType]

    @app.post("/evidence")
    def upload_evidence(req: EvidenceUpload, request: Request):
        """Store an off-chain evidence artifact; returns the {name, sha256,
        uri} reference to embed in an event so substitution is detectable."""
        _limit(request, "evidence", 20, 60)
        import base64
        name = _SAFE_NAME.sub("_", os.path.basename(req.name)).strip(" .")
        if not name or len(name) > 100:
            raise HTTPException(400, "artifact name must be 1-100 safe characters")
        try:
            data = base64.b64decode(req.content_base64, validate=True)
        except Exception:
            raise HTTPException(400, "content_base64 is not valid base64")
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(413, "evidence artifact larger than 5 MB")
        return evidence.put(name, data)

    @app.get("/head")
    def head():
        evs = ledger.all()
        return {"height": len(evs),
                "head_hash": evs[-1].event_hash if evs else GENESIS_HASH}

    @app.post("/events/prepare")
    def prepare_event(req: PrepareEvent, request: Request):
        """Two-phase signed submission (roadmap step 5: authenticated ledger
        APIs). The server assembles the exact canonical signing body —
        including event_id and current prev_hash — and returns it. The client
        signs canonical_json(body) locally with its own private key, then
        calls /events/commit. The server never holds participant keys."""
        _limit(request, "prepare", 120, 60)
        if len(canonical_json(req.payload)) > MAX_PAYLOAD_BYTES:
            raise HTTPException(413, "payload too large")
        if len(req.evidence) > MAX_EVIDENCE_REFS:
            raise HTTPException(413, f"more than {MAX_EVIDENCE_REFS} evidence references")
        try:
            etype = EventType(req.event_type)
        except ValueError:
            raise HTTPException(400, f"unknown event type {req.event_type}")
        try:
            org = registry.get(req.actor_org)
        except PermissionError_ as e:
            raise HTTPException(403, str(e))
        if not any(r in PERMISSIONS[etype] for r in org.roles):
            raise HTTPException(403, f"role not permitted to submit {etype.value}")
        missing = [f for f in REQUIRED_FIELDS[etype] if f not in req.payload]
        if missing:
            raise HTTPException(422, f"missing fields: {missing}")
        prev_hash = getattr(ledger, "head_hash", GENESIS_HASH)
        body = {
            "event_id": str(uuid.uuid4()),
            "event_type": etype.value,
            "subject_id": req.subject_id,
            "actor_org": req.actor_org,
            "timestamp": time.time(),
            "payload": req.payload,
            "evidence": req.evidence,
            "prev_hash": prev_hash,
        }
        return {"body": body}

    @app.post("/events/commit")
    def commit_event(req: CommitEvent, request: Request):
        _limit(request, "commit", 60, 60)
        body = req.body

        # strict body shape: exactly the signing-body keys, sane types
        if set(body.keys()) != _BODY_KEYS:
            raise HTTPException(422, "body must contain exactly the keys returned by /events/prepare")
        if not all(isinstance(body[k], str) for k in
                   ("event_id", "event_type", "subject_id", "actor_org", "prev_hash")):
            raise HTTPException(422, "malformed body")
        if not isinstance(body["timestamp"], (int, float)) \
                or not isinstance(body["payload"], dict) or not isinstance(body["evidence"], list):
            raise HTTPException(422, "malformed body")
        try:
            etype = EventType(body["event_type"])
        except ValueError:
            raise HTTPException(400, f"unknown event type {body['event_type']}")
        try:
            org = registry.get(body["actor_org"])
        except PermissionError_ as e:
            raise HTTPException(403, str(e))
        # a valid signature is not enough: the role must also permit the event
        if not any(r in PERMISSIONS[etype] for r in org.roles):
            raise HTTPException(403, f"role not permitted to submit {etype.value}")
        missing = [f for f in REQUIRED_FIELDS[etype] if f not in body["payload"]]
        if missing:
            raise HTTPException(422, f"missing fields: {missing}")
        if len(canonical_json(body["payload"])) > MAX_PAYLOAD_BYTES:
            raise HTTPException(413, "payload too large")
        if len(body["evidence"]) > MAX_EVIDENCE_REFS or not all(
                isinstance(e, dict) and isinstance(e.get("name"), str)
                and isinstance(e.get("sha256"), str) and isinstance(e.get("uri"), str)
                for e in body["evidence"]):
            raise HTTPException(422, "malformed evidence references")

        canon = canonical_json(body)
        if not verify_signature(org.public_key, canon, req.signature):
            raise HTTPException(401, "signature does not verify against registered key")

        try:
            with write_lock:
                ev = ledger.commit_prepared(body, req.signature)
        except PermissionError_ as exc:
            raise HTTPException(403, str(exc))
        except LedgerError as exc:
            message = str(exc)
            status = 409 if any(word in message.lower() for word in ("already", "advanced", "workflow", "next allowed", "first required", "current step")) else 422
            raise HTTPException(status, message)
        return {"event_id": ev.event_id, "event_hash": ev.event_hash}

    @app.get("/passport/issuer")
    def passport_issuer():
        """The public key that verifies signed PDF passport attestations.
        Fetch it over HTTPS from the official domain as your trust anchor."""
        if passport_signer is None:
            raise HTTPException(503, "passport issuer not configured")
        return {"algorithm": "ed25519", "public_key": passport_signer.public_hex}

    @app.post("/passport/verify")
    def passport_verify(att: VerifyAttestation):
        """Verify a signed PDF passport attestation: checks the issuer's
        signature and reports whether the snapshot still matches the live
        passport (it may differ once new scans or corrections are appended)."""
        if passport_signer is None:
            raise HTTPException(503, "passport issuer not configured")
        signed_core = {
            "type": att.type, "version": att.version, "batch_id": att.batch_id,
            "content_sha256": att.content_sha256, "ledger_head_hash": att.ledger_head_hash,
            "ledger_height": att.ledger_height, "ledger_verified": att.ledger_verified,
            "issued_at": att.issued_at,
        }
        sig_ok = verify_signature(passport_signer.public_hex,
                                  canonical_json(signed_core), att.signature)
        matches_live = None
        if sig_ok and _batch_exists(att.batch_id):
            live = build_passport(ledger, att.batch_id, evidence)
            matches_live = sha256_hex(canonical_json(live)) == att.content_sha256
        return {"signature_valid": sig_ok, "matches_live_passport": matches_live,
                "current_height": len(ledger), "issued_at": att.issued_at}

    @app.get("/passport/{batch_id}.pdf")
    def passport_pdf(batch_id: str, request: Request, lang: str = "en"):
        """Signed PDF passport: a tamper-evident snapshot bound to the ledger
        by an Ed25519 attestation, with a QR back to the live verifier."""
        if passport_signer is None:
            raise HTTPException(503, "passport issuer not configured")
        if not _batch_exists(batch_id):
            raise HTTPException(404, f"unknown batch {batch_id}")
        from .passport_pdf import build_passport_pdf
        data = build_passport(ledger, batch_id, evidence)
        evs = ledger.all()
        head = evs[-1].event_hash if evs else GENESIS_HASH
        verify_url = str(request.base_url).rstrip("/") + "/m?batch=" + quote(batch_id, safe="")
        pdf_bytes, _ = build_passport_pdf(
            data, signer=passport_signer, issuer_pub=passport_signer.public_hex,
            head_hash=head, height=len(evs), verify_url=verify_url, lang=lang)
        fname = f"olivechain-passport-{batch_id}.pdf"
        return Response(pdf_bytes, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{fname}"'})

    @app.get("/passport/{batch_id}/credential")
    def passport_credential(batch_id: str, request: Request):
        """The passport as a W3C Verifiable Credential (VC 2.0) signed with an
        eddsa-jcs-2022 Data Integrity proof. Self-verifiable offline; the
        issuer is a did:key derived from the passport issuer's Ed25519 key."""
        if passport_signer is None:
            raise HTTPException(503, "passport issuer not configured")
        if not _batch_exists(batch_id):
            raise HTTPException(404, f"unknown batch {batch_id}")
        from .credentials import build_passport_credential, gs1_digital_link
        data = build_passport(ledger, batch_id, evidence)
        evs = ledger.all()
        head = evs[-1].event_hash if evs else GENESIS_HASH
        base = str(request.base_url).rstrip("/")
        vc = build_passport_credential(
            data, signer=passport_signer, head_hash=head, height=len(evs),
            content_sha256=sha256_hex(canonical_json(data)),
            credential_id=f"{base}/passport/{quote(batch_id, safe='')}/credential",
            subject_id=gs1_digital_link(base, GTIN, batch_id))
        return JSONResponse(vc, media_type="application/ld+json")

    @app.post("/credentials/verify")
    def credentials_verify(vc: dict = Body(...)):
        """Verify a passport Verifiable Credential's Data Integrity proof, and
        report whether its issuer is the one this server recognizes."""
        from .credentials import did_key_ed25519, verify_passport_credential
        res = verify_passport_credential(vc)
        if passport_signer is not None:
            res["issuer_recognized"] = (
                res.get("issuer") == did_key_ed25519(passport_signer.public_hex))
        return res

    @app.get("/01/{gtin}/10/{lot}", include_in_schema=False)
    def gs1_resolve(gtin: str, lot: str):
        """GS1 Digital Link resolver: /01/{GTIN}/10/{lot} -> mobile verifier."""
        return RedirectResponse("/m?batch=" + quote(lot, safe=""))

    @app.get("/passport/{batch_id}")
    def passport(batch_id: str):
        if not _batch_exists(batch_id):
            raise HTTPException(404, f"unknown batch {batch_id}")
        result = build_passport(ledger, batch_id, evidence)
        try:
            result["workflow_status"] = _workflow_status(batch_id)
        except Exception as exc:
            result["workflow_status"] = {
                "subject_id": batch_id, "workflow": "product",
                "exists": True, "valid": False, "complete": False,
                "message": f"status unavailable: {exc}",
            }
        return result

    @app.get("/residues/{residue_id}/balance")
    def balance(residue_id: str):
        rec = reconcile_residue(ledger, residue_id)
        return rec.__dict__

    @app.get("/audit")
    def audit():
        ok, problems = ledger.verify_chain()
        return {"chain_valid": ok, "problems": problems,
                "anomalies": [f.__dict__ for f in anomaly.scan(ledger)]}

    @app.get("/rewards/due")
    def rewards_due():
        """Rewards currently due and verifiable, computed read-only. The
        authority issues them by signing reward_issued events itself (via
        /events/prepare + /events/commit) — the server holds no signing key."""
        due = due_rewards(ledger)
        for d in due:
            d["recipient_name"] = _org_name(d["recipient"])
        return due

    @app.get("/governance")
    def governance():
        """The authority's worklist: open review flags (with the flagged
        event's summary), anomalies not yet flagged, and rewards due."""
        flags = list(ledger.iter_type(EventType.REVIEW_FLAG))
        resolved = {ev.payload["flag_event"]
                    for ev in ledger.iter_type(EventType.REVIEW_RESOLUTION)}
        flagged_subjects = {ev.payload["subject_event"] for ev in flags}
        open_list = []
        for ev in flags:
            if ev.event_id in resolved:
                continue
            summary = None
            try:
                tgt = ledger.get(ev.payload["subject_event"])
                summary = {"event_type": tgt.event_type, "subject_id": tgt.subject_id,
                           "actor_org": tgt.actor_org, "actor_name": _org_name(tgt.actor_org),
                           "timestamp": tgt.timestamp, "payload": tgt.payload,
                           "superseded_by": tgt.superseded_by}
            except KeyError:
                pass
            open_list.append({"flag_event": ev.event_id, "timestamp": ev.timestamp,
                              "rule": ev.payload["rule"], "detail": ev.payload["detail"],
                              "subject_event": ev.payload["subject_event"],
                              "flagged": summary})
        unflagged = [f.__dict__ for f in anomaly.scan(ledger)
                     if f.subject_event not in flagged_subjects]
        return {"open_flags": open_list, "unflagged_anomalies": unflagged,
                "due_rewards": due_rewards(ledger)}

    @app.get("/rewards/balances")
    def balances():
        # Balances are derivable read-only from REWARD_ISSUED events; the
        # signing engine is only needed to issue new rewards.
        bal: dict[str, int] = {}
        for ev in ledger.iter_type(EventType.REWARD_ISSUED):
            if ev.superseded_by:
                continue
            p = ev.payload
            bal[p["recipient"]] = bal.get(p["recipient"], 0) + int(p["amount"])
        return [{"org_id": oid, "name": _org_name(oid), "points": pts}
                for oid, pts in sorted(bal.items(), key=lambda kv: -kv[1])]

    @app.post("/rewards/run")
    def run_rewards():
        if engine is None:
            raise HTTPException(503, "incentive engine not configured")
        with write_lock:
            return engine.run()

    return app
