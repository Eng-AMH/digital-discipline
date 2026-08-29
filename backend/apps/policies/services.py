"""
Policy engine services — the real logic behind §5, §9, §10, §11, §43.

This module is where "policies are just database rows" becomes "policies are
cryptographically resolved, signed, and safely enforceable offline." Every function
here corresponds to a specific numbered decision in
docs/01-REQUIREMENTS-AND-ARCHITECTURE.md §5.
"""
import base64
import json
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature

from apps.core.models import write_audit_log, AuditLog


# ---------------------------------------------------------------------------
# Server signing key handling
#
# In production this key is generated once, stored in a secrets manager (not in
# the repo, not in Django settings source), and loaded via environment variable.
# `UNLOCK_TOKEN_SIGNING_KEY_B64` is read from settings, which itself reads from
# the environment — see config/settings.py and .env.example.
# ---------------------------------------------------------------------------

def _server_private_key() -> Ed25519PrivateKey:
    raw = base64.b64decode(settings.UNLOCK_TOKEN_SIGNING_KEY_B64)
    return Ed25519PrivateKey.from_private_bytes(raw)


def server_public_key_b64() -> str:
    """
    Returned to devices at registration time so they can verify server-signed
    payloads (unlock tokens, offline policy blobs) without a network call each
    time — this public key is what gets "pinned in the app" per architecture §5.3.
    """
    pub = _server_private_key().public_key()
    raw = pub.public_bytes_raw()
    return base64.b64encode(raw).decode()


def _canonical_json(payload: dict) -> bytes:
    # sort_keys=True is essential: the device must reconstruct byte-identical JSON
    # to verify the signature. Any dict-ordering mismatch would break verification
    # even with the correct key, so this canonicalization is the actual contract
    # between server-signing and device-verifying code — documented explicitly so
    # the Android implementation matches it exactly (see android module).
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_payload(payload: dict) -> str:
    signature = _server_private_key().sign(_canonical_json(payload))
    return base64.b64encode(signature).decode()


def verify_device_signature(device_public_key_b64: str, payload: dict, signature_b64: str) -> bool:
    """
    Used to verify requests a DEVICE signs with ITS OWN private key (e.g. heartbeat,
    unlock-token redemption confirmation) — the reverse direction of sign_payload
    above. This is the "signed request" half of architecture §5.2's device identity
    model: the server never sees the device's private key, only verifies against the
    public key it stored at registration.
    """
    try:
        raw_pub = base64.b64decode(device_public_key_b64)
        pub = Ed25519PublicKey.from_public_bytes(raw_pub)
        pub.verify(base64.b64decode(signature_b64), _canonical_json(payload))
        return True
    except (InvalidSignature, ValueError):
        return False


# ---------------------------------------------------------------------------
# §5 Weekly Locked Plan — the "no changing your mind mid-weakness" guard
# ---------------------------------------------------------------------------

def can_modify_limit(*, user, weekly_plan_ids: list, new_daily_minutes: int, current_daily_minutes: int) -> bool:
    """
    Blueprint intent, quoted directly in the model docstring: prevent loosening a
    limit while a WeeklyPlan lock is active. TIGHTENING (lowering the limit) is
    always allowed — locking exists to prevent self-sabotage, not to prevent
    someone from being MORE strict with themselves mid-week.
    """
    if new_daily_minutes <= current_daily_minutes:
        return True  # tightening or unchanged — always fine

    from apps.policies.models import WeeklyPlan

    active_locks = WeeklyPlan.objects.filter(
        id__in=weekly_plan_ids, user=user, is_confirmed=True
    )
    for plan in active_locks:
        if plan.is_currently_locked():
            return False
    return True


def assert_hard_lock_allowed(user):
    """
    Architecture doc §9: server-side consent gate. Raises PermissionDenied (→ DRF
    403) unless the user has completed BOTH permissions-explained and consent-given
    steps of onboarding. This is checked in the view layer before creating any
    policy with a hard-lock semantic (WeeklyPlan.is_hard_locked=True in particular).
    """
    state = getattr(user, "onboarding_state", None)
    if state is None or not state.is_hard_lock_consented():
        write_audit_log(
            AuditLog.EventType.POLICY_MODIFICATION_BLOCKED,
            actor=user,
            metadata={"reason": "onboarding_consent_incomplete"},
        )
        raise PermissionDenied(
            "Hard-lock policies require completed onboarding consent "
            "(permissions explained + consent given)."
        )


# ---------------------------------------------------------------------------
# §11 Unlock token minting/redemption
# ---------------------------------------------------------------------------

def mint_unlock_token(*, unlock_request):
    """
    Architecture §5.3 steps 1-2. Called after an UnlockRequest transitions to
    APPROVED (or AUTO_APPROVED). Builds, signs, and persists exactly one
    UnlockToken — the OneToOneField on UnlockToken.request enforces "exactly one"
    at the schema level, not just by convention.
    """
    from apps.policies.models import UnlockToken

    now = timezone.now()
    expires_at = now + timedelta(hours=6)

    token = UnlockToken(
        request=unlock_request,
        device=unlock_request.device,
        package_name=unlock_request.package_name,
        granted_minutes=unlock_request.requested_minutes,
        expires_at=expires_at,
    )
    # nonce has a default=uuid4 on the model, but we need its value NOW to include
    # in the signed payload, so we resolve it before signing rather than relying on
    # the field default being materialized before our own logic runs.
    import uuid
    token.nonce = uuid.uuid4()

    payload = {
        "device_id": str(unlock_request.device_id),
        "package_name": unlock_request.package_name,
        "granted_minutes": unlock_request.requested_minutes,
        "nonce": str(token.nonce),
        "issued_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    token.payload = payload
    token.signature = sign_payload(payload)
    token.save()

    write_audit_log(
        AuditLog.EventType.UNLOCK_TOKEN_ISSUED,
        actor=unlock_request.user,
        target=token,
        metadata={"package_name": token.package_name, "granted_minutes": token.granted_minutes},
    )
    return token


def redeem_unlock_token(*, token_id, device):
    """
    Called when a device reports it has applied an unlock token (§5.3 step 3-4).
    Idempotency + replay protection: a token can only be redeemed once
    (`redeemed_at` null-check), and a second attempt is logged as a security event
    rather than silently ignored, per architecture §5.3.
    """
    from apps.policies.models import UnlockToken

    try:
        token = UnlockToken.objects.select_related("device").get(id=token_id, device=device)
    except UnlockToken.DoesNotExist:
        return None, "not_found"

    if token.redeemed_at is not None:
        write_audit_log(
            AuditLog.EventType.UNLOCK_TOKEN_REPLAY_BLOCKED,
            target=token,
            metadata={"device_id": str(device.id)},
        )
        return None, "already_redeemed"

    if timezone.now() > token.expires_at:
        return None, "expired"

    token.redeemed_at = timezone.now()
    token.save(update_fields=["redeemed_at"])

    write_audit_log(
        AuditLog.EventType.UNLOCK_TOKEN_REDEEMED,
        target=token,
        metadata={"package_name": token.package_name, "granted_minutes": token.granted_minutes},
    )
    return token, None


# ---------------------------------------------------------------------------
# §43 Offline Mode — signed policy blob
# ---------------------------------------------------------------------------

def build_signed_policy_blob(*, user, device, valid_hours: int = 6):
    """
    Architecture §5.4. Resolves ALL active policy for a user into one payload the
    device can enforce entirely offline until `valid_until`. This is the function
    that makes §43's requirement real: "الجهاز لا يحتاج الإنترنت في كل ثانية."

    The resolution here is deliberately the FULL effective policy (app limits +
    website limits + active schedules + focus session state), not a diff — devices
    always apply a complete, self-consistent snapshot rather than reconciling
    incremental patches, which avoids an entire class of offline-sync bugs.
    """
    from apps.policies.models import AppLimit, WebsiteLimit, Schedule, FocusSession

    now = timezone.now()
    valid_until = now + timedelta(hours=valid_hours)

    app_limits = list(
        AppLimit.objects.filter(user=user, is_enabled=True).values(
            "package_name", "display_name", "daily_minutes"
        )
    )
    website_limits = list(
        WebsiteLimit.objects.filter(user=user, is_enabled=True).values(
            "domain", "category", "daily_minutes"
        )
    )
    schedules = list(
        Schedule.objects.filter(user=user, is_enabled=True).values(
            "mode", "start_time", "end_time", "days_of_week", "blocked_packages", "allowed_packages"
        )
    )
    active_focus_session = (
        FocusSession.objects.filter(user=user, device=device, status=FocusSession.Status.ACTIVE)
        .values("id", "planned_minutes", "allowed_packages", "blocked_packages", "started_at")
        .first()
    )

    payload = {
        "user_id": str(user.id),
        "device_id": str(device.id),
        "issued_at": now.isoformat(),
        "valid_until": valid_until.isoformat(),
        "app_limits": app_limits,
        "website_limits": website_limits,
        "schedules": schedules,
        "active_focus_session": active_focus_session,
    }
    # Non-JSON-native types (TimeField, dict with UUID) need explicit stringification
    # before canonical signing — done via json.dumps default=str for anything
    # datetime/UUID/time-typed that slips through .values() as a Python object.
    normalized = json.loads(json.dumps(payload, default=str))

    signature = sign_payload(normalized)
    return {"payload": normalized, "signature": signature}
