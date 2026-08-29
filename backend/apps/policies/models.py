"""
Policies: the actual product. Daily limits (§4), Weekly Locked Plans (§5), Website
Blocking (§6), Focus Mode (§7), Smart Schedules (§8), Exam Mode (§9), Secure Unlock
(§10), Device-Specific Unlock crypto (§11).

Design decision (architecture doc §4): UnlockRequest and UnlockToken are separate
models on purpose.
  - UnlockRequest = the human workflow object. §25 Accountability Partner approves or
    rejects a REQUEST. It has no cryptographic material.
  - UnlockToken = the cryptographic, device-specific, one-time, time-limited, audited
    object (§11) actually redeemed on-device to lift a restriction.
An approved UnlockRequest causes an UnlockToken to be minted; they are not the same
row, because "a human said yes" and "here is signed proof a device can verify offline"
are different concerns with different lifecycles (a request is decided once; a token
can be redeemed, expire, or be replayed-and-rejected).

Design decision: policies belong to User, never to Device (see apps.devices module
docstring) — this file's models all FK to User, and a Device only ever RECEIVES a
resolved, signed snapshot of them (see apps.policies.services.build_signed_policy_blob,
implementing architecture doc §5.4 offline mode).
"""
import uuid

from django.conf import settings
from django.db import models

from apps.core.models import TimestampedModel, UUIDModel


class AppLimit(UUIDModel, TimestampedModel):
    """§4 Daily App Limits — one row per (user, app package)."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="app_limits")
    package_name = models.CharField(max_length=255, help_text="e.g. com.instagram.android")
    display_name = models.CharField(max_length=100, help_text="e.g. Instagram")
    daily_minutes = models.PositiveIntegerField()
    is_enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "package_name"], name="unique_user_app_limit"),
        ]

    def __str__(self):
        return f"{self.display_name}: {self.daily_minutes}m/day for {self.user.email}"


class WebsiteCategory(models.TextChoices):
    """
    §3 Website Categories. "SHORT_FORM" groups TikTok/Reels/Shorts/Facebook-Reels as
    ONE limit target. Honest limitation (architecture doc §3.1 point 3): this works
    cleanly when each is a distinct app (blocked via AccessibilityService) or distinct
    domain (blocked via VPN/DNS). It CANNOT distinguish youtube.com/shorts from the
    rest of youtube.com — VPN-based DNS filtering has no path-level visibility. The
    dashboard must surface this limitation explicitly rather than imply path-level
    blocking works.
    """
    SHORT_FORM = "SHORT_FORM", "Short-form Content"
    SOCIAL_MEDIA = "SOCIAL_MEDIA", "Social Media"
    NEWS = "NEWS", "News"
    ENTERTAINMENT = "ENTERTAINMENT", "Entertainment"
    CUSTOM = "CUSTOM", "Custom"


class WebsiteLimit(UUIDModel, TimestampedModel):
    """§6 Website Blocking. Enforced on Android via VpnService DNS filtering — see
    architecture doc §3.1 point 3 for the domain-level-only honesty boundary."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="website_limits")
    domain = models.CharField(max_length=255, help_text="e.g. tiktok.com")
    category = models.CharField(max_length=32, choices=WebsiteCategory.choices, default=WebsiteCategory.CUSTOM)
    daily_minutes = models.PositiveIntegerField(null=True, blank=True, help_text="Null = fully blocked, not time-limited")
    is_enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "domain"], name="unique_user_website_limit"),
        ]


class WeeklyPlan(UUIDModel, TimestampedModel):
    """
    §5 Weekly Locked Plan + §9 Exam Mode (modeled as a WeeklyPlan subtype, per
    architecture doc §2 traceability table — Exam Mode is the same locking mechanism
    with a longer duration and is_locked_hard=True by default).

    The core anti-impulse mechanism: once CONFIRMED, `locked_until` prevents the
    underlying AppLimit/WebsiteLimit rows referenced by this plan from being loosened
    (tightening is still allowed — see apps.policies.services.can_modify_limit) until
    that timestamp, addressing the blueprint's explicit design intent: "الفكرة تمنع
    المستخدم من تغيير الحد في لحظة ضعف."
    """

    class PlanType(models.TextChoices):
        WEEKLY = "WEEKLY", "Weekly Plan"
        EXAM_MODE = "EXAM_MODE", "Exam Mode"

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="weekly_plans")
    plan_type = models.CharField(max_length=16, choices=PlanType.choices, default=PlanType.WEEKLY)
    app_limits = models.ManyToManyField(AppLimit, blank=True, related_name="weekly_plans")
    website_limits = models.ManyToManyField(WebsiteLimit, blank=True, related_name="weekly_plans")

    is_confirmed = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    locked_until = models.DateTimeField(null=True, blank=True)

    # §9 Exam Mode: "يمكن جعلها مقفلة طوال فترة الامتحانات" — hard lock disallows even
    # the Secure Unlock (§10) extra-time flow, not just direct limit edits. Regular
    # WEEKLY plans still permit Secure Unlock requests during the lock window.
    is_hard_locked = models.BooleanField(
        default=False,
        help_text="If true, blocks Secure Unlock requests too, not just direct edits (Exam Mode).",
    )

    class Meta:
        indexes = [models.Index(fields=["user", "locked_until"])]

    def is_currently_locked(self) -> bool:
        if not self.is_confirmed or self.locked_until is None:
            return False
        from django.utils import timezone
        return timezone.now() < self.locked_until


class ScheduleMode(models.TextChoices):
    """§8 Smart Schedules named modes."""
    STUDY = "STUDY", "Study Mode"
    FOCUS = "FOCUS", "Focus Mode"
    SLEEP = "SLEEP", "Sleep Mode"
    CUSTOM = "CUSTOM", "Custom Mode"


class Schedule(UUIDModel, TimestampedModel):
    """
    §8 Smart Schedules. Recurring time windows where a named mode's restrictions
    apply automatically. `days_of_week` as a bitmask-ish list of ints (0=Mon..6=Sun)
    keeps this simple to resolve without a separate join table for "which days."
    """

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="schedules")
    mode = models.CharField(max_length=16, choices=ScheduleMode.choices)
    label = models.CharField(max_length=100, blank=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    days_of_week = models.JSONField(default=list, help_text="List of ints, 0=Monday..6=Sunday")
    is_enabled = models.BooleanField(default=True)

    # For STUDY/FOCUS modes, which packages get blocked during the window; for SLEEP,
    # typically "all except allowlist." Kept as explicit lists rather than inferring
    # from AppLimit, since a schedule's restriction set can differ from daily limits
    # (e.g. TikTok fully blocked 09:00-14:00 even though its daily limit is 45m).
    blocked_packages = models.JSONField(default=list)
    allowed_packages = models.JSONField(
        default=list, help_text="Essential-app allowlist, e.g. Phone/Messages/Maps (§7 Focus Mode)"
    )


class FocusSession(UUIDModel, TimestampedModel):
    """§7 Focus Mode + §26 Digital Detox (session_type differentiates duration/intent)
    + §28 Earn Your Scroll (completion triggers a token grant, see apps.gamification)."""

    class SessionType(models.TextChoices):
        FOCUS = "FOCUS", "Focus Session"
        DETOX = "DETOX", "Digital Detox"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        ABANDONED = "ABANDONED", "Abandoned (ended early)"

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="focus_sessions")
    device = models.ForeignKey("devices.Device", on_delete=models.CASCADE, related_name="focus_sessions")
    session_type = models.CharField(max_length=16, choices=SessionType.choices, default=SessionType.FOCUS)
    planned_minutes = models.PositiveIntegerField()
    allowed_packages = models.JSONField(default=list, help_text="Essential apps allowed during session, §7")
    blocked_packages = models.JSONField(default=list)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    actual_minutes = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "status"])]


class UnlockRequest(UUIDModel, TimestampedModel):
    """
    §10 Secure Unlock / §25 Accountability Partner / §47 Emergency Mode.
    The HUMAN workflow object — see module docstring for why this is split from
    UnlockToken. An approved request causes exactly one UnlockToken to be minted
    (see apps.policies.services.approve_unlock_request).
    """

    class ReasonType(models.TextChoices):
        STANDARD = "STANDARD", "Standard extra time"
        ACCOUNTABILITY = "ACCOUNTABILITY", "Accountability partner approval"
        EMERGENCY = "EMERGENCY", "Emergency"
        REWARDED_AD = "REWARDED_AD", "Rewarded ad unlock"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        AUTO_APPROVED = "AUTO_APPROVED", "Auto-approved (free tier allowance / rewarded ad)"
        EXPIRED = "EXPIRED", "Expired without decision"

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="unlock_requests")
    device = models.ForeignKey("devices.Device", on_delete=models.CASCADE, related_name="unlock_requests")
    package_name = models.CharField(max_length=255)
    requested_minutes = models.PositiveIntegerField()
    reason_type = models.CharField(max_length=16, choices=ReasonType.choices, default=ReasonType.STANDARD)
    reason_note = models.CharField(max_length=280, blank=True, help_text="e.g. 'Important task'")

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    # §25: the accountability partner is a User (a friend/family member with a
    # confirmed AccountabilityLink, see apps.social), not a free-text field.
    approver = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="unlock_decisions_made",
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "status"])]


def _default_token_expiry():
    from django.utils import timezone
    from datetime import timedelta
    return timezone.now() + timedelta(hours=6)


class UnlockToken(UUIDModel):
    """
    §11 Device-Specific Unlock System. The cryptographic object. Minted from an
    approved UnlockRequest by apps.policies.services.mint_unlock_token, which:
      1. Builds the payload {device_id, package_name, granted_minutes, nonce, issued_at, expires_at}
      2. Signs it with the SERVER's Ed25519 private key (settings.UNLOCK_TOKEN_SIGNING_KEY,
         never the device's key — the device only ever VERIFIES this signature)
      3. Stores signature + payload here for audit and replay-protection
      4. The device verifies against the server's pinned public key and applies the
         grant locally — this is what makes it usable even briefly offline.

    `nonce` + unique constraint is what makes redemption replay-proof: a second
    redemption attempt with the same nonce fails at the DB level, and is logged as
    UNLOCK_TOKEN_REPLAY_BLOCKED in AuditLog (architecture doc §5.3 step 3).
    """

    request = models.OneToOneField(UnlockRequest, on_delete=models.CASCADE, related_name="token")
    device = models.ForeignKey("devices.Device", on_delete=models.CASCADE, related_name="unlock_tokens")
    package_name = models.CharField(max_length=255)
    granted_minutes = models.PositiveIntegerField()

    nonce = models.UUIDField(default=uuid.uuid4, unique=True)
    payload = models.JSONField(help_text="Exact signed payload, for signature re-verification/debugging")
    signature = models.TextField(help_text="Base64 Ed25519 signature of `payload`, server-signed")

    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_default_token_expiry)
    redeemed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["device", "redeemed_at"])]
