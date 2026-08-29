"""
Devices: identity, health, usage telemetry.

Design decisions (architecture doc §4, §5.2):
- Device stores only the PUBLIC half of an Ed25519 keypair. The private key is
  generated on-device (Android Keystore, hardware-backed where available) and never
  transmitted. This is the literal implementation of blueprint §11: "لا نخزن الـ
  Secret الخام في قاعدة البيانات."
- ActivityLog (usage telemetry, e.g. "used TikTok for 4 minutes") is a SEPARATE model
  from apps.core.AuditLog (security events) and DeviceEvent (lifecycle) below — see
  architecture doc §4 for why conflating these would make the audit trail useless.
- Policies belong to User (apps.policies), not Device. Device only BINDS to and
  CACHES policy — this is what makes §40 Backup & Recovery possible: delete/replace
  a device, re-register, and the account's policies are simply re-synced.
"""
from django.db import models

from apps.core.models import TimestampedModel, UUIDModel


class Device(UUIDModel, TimestampedModel):
    """A registered physical device bound to a User account."""

    class Platform(models.TextChoices):
        ANDROID = "ANDROID", "Android"
        IOS = "IOS", "iOS"
        WEB = "WEB", "Web (PWA companion, read-only for enforcement)"

    class EnrollmentType(models.TextChoices):
        STANDARD = "STANDARD", "Standard (AccessibilityService + VpnService, user-revocable)"
        DEVICE_OWNER = (
            "DEVICE_OWNER",
            "Device Owner (Android Enterprise provisioning — Family/School plans only)",
        )
        # See architecture doc §3.1 point 5: DEVICE_OWNER is modeled now for forward
        # compatibility but no provisioning flow ships in this phase.

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="devices")
    platform = models.CharField(max_length=16, choices=Platform.choices)
    enrollment_type = models.CharField(
        max_length=16, choices=EnrollmentType.choices, default=EnrollmentType.STANDARD
    )

    name = models.CharField(max_length=100, help_text="User-facing label, e.g. 'Ahmed's Phone'")
    model_name = models.CharField(max_length=100, blank=True)
    os_version = models.CharField(max_length=50, blank=True)
    app_version = models.CharField(max_length=20, blank=True)

    # Ed25519 PUBLIC key only, base64-encoded. See module docstring — this is the
    # entire device-identity security model in one field.
    public_key = models.TextField(unique=True)

    is_active = models.BooleanField(default=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)

    # §9 Anti-Tamper / Device Health — these booleans are set by the device's own
    # heartbeat payload (self-reported, verified by signature — see apps.devices.services)
    # and drive the "⚠ Protection Interrupted" banner. Per architecture doc §3.1 point 4,
    # this can only ever DETECT, never PREVENT, the user disabling these services.
    accessibility_service_active = models.BooleanField(default=False)
    vpn_service_active = models.BooleanField(default=False)
    usage_access_granted = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["last_heartbeat_at"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.platform}) — {self.user.email}"

    @property
    def is_healthy(self) -> bool:
        """Device Health Dashboard §9 top-line status."""
        if self.platform != self.Platform.ANDROID:
            return True  # iOS/Web health semantics differ; not evaluated here yet.
        return self.accessibility_service_active and self.usage_access_granted


class DeviceEvent(UUIDModel):
    """
    Device lifecycle events (registered, key rotated, went offline, tamper signal
    RECEIVED — the raw event; the AuditLog row is the audit-trail RECORD of it).
    Kept separate from AuditLog per architecture doc §4: this is high-volume,
    device-generated, offline-batched telemetry, not the curated security trail.
    """

    class EventType(models.TextChoices):
        REGISTERED = "REGISTERED", "Registered"
        HEARTBEAT = "HEARTBEAT", "Heartbeat"
        ACCESSIBILITY_ENABLED = "ACCESSIBILITY_ENABLED", "Accessibility service enabled"
        ACCESSIBILITY_DISABLED = "ACCESSIBILITY_DISABLED", "Accessibility service disabled"
        VPN_ENABLED = "VPN_ENABLED", "VPN filter enabled"
        VPN_DISABLED = "VPN_DISABLED", "VPN filter disabled"
        WENT_OFFLINE = "WENT_OFFLINE", "Went offline"
        CAME_ONLINE = "CAME_ONLINE", "Came online"
        APP_UNINSTALL_ATTEMPTED = "APP_UNINSTALL_ATTEMPTED", "App uninstall attempted (DeviceAdmin)"

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(help_text="Device-reported time (may be offline-batched)")
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["device", "-occurred_at"])]


class ActivityLog(UUIDModel):
    """
    Core usage telemetry — the raw material for §12 Dashboard, §16 Analytics, §19
    Focus Score, §18 Smart Limits. One row per (device, app-or-domain, time-bucket).

    Devices batch these locally (Room DB on Android, per architecture doc §5.4
    offline-first design) and sync in bulk — `synced_at` vs `occurred_date`/`minutes`
    distinguishes "when this happened" from "when we found out."
    """

    class TargetType(models.TextChoices):
        APP = "APP", "Installed app"
        WEBSITE = "WEBSITE", "Website / domain"

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="activity_logs")
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="activity_logs",
        help_text="Denormalized from device.user for query performance on analytics — "
                   "this table is large and account-level rollups are the common query.",
    )
    target_type = models.CharField(max_length=16, choices=TargetType.choices)
    target_identifier = models.CharField(
        max_length=255, help_text="Package name (e.g. com.instagram.android) or domain"
    )
    occurred_date = models.DateField(db_index=True)
    minutes_used = models.PositiveIntegerField()
    session_started_at = models.DateTimeField()
    session_ended_at = models.DateTimeField()
    synced_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "occurred_date"]),
            models.Index(fields=["device", "occurred_date"]),
            models.Index(fields=["user", "target_identifier", "occurred_date"]),
        ]
