"""
Core abstractions shared across the platform.

Design decision (see docs/01-REQUIREMENTS-AND-ARCHITECTURE.md §4):
AuditLog is deliberately separate from ActivityLog (usage telemetry, in apps.devices)
and DeviceEvent (device lifecycle, in apps.devices). AuditLog covers ONLY
security-relevant events: unlock issuance/redemption, policy changes, device
registration, tamper detection, subscription changes, family permission changes.
Mixing "watched TikTok for 4 minutes" with "approved a 30-minute unlock" in one table
would make the security audit trail practically unusable.
"""
import uuid

from django.conf import settings
from django.db import models


class UUIDModel(models.Model):
    """Abstract base: UUID primary key instead of auto-increment integer.

    Chosen deliberately for every user-facing/externally-referenced model so that
    IDs are non-enumerable (you cannot discover other users' policy IDs by
    incrementing an integer) and so that device-generated records (created
    offline, synced later) never collide with server-generated ones.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimestampedModel(models.Model):
    """Abstract base: created_at/updated_at on everything, for auditability."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLog(UUIDModel, models.Model):
    """
    Append-only security audit trail.

    Rows are never updated or deleted through normal application code (enforced by
    convention + admin read-only registration, see apps.core.admin). This is the
    concrete implementation of blueprint §51 "Audit Logs" and directly supports
    §11's requirement that every unlock operation "لها سجل" (has a record).
    """

    class EventType(models.TextChoices):
        # Auth & account
        LOGIN_SUCCESS = "LOGIN_SUCCESS", "Login succeeded"
        LOGIN_FAILED = "LOGIN_FAILED", "Login failed"
        PASSWORD_CHANGED = "PASSWORD_CHANGED", "Password changed"
        TWO_FA_ENABLED = "TWO_FA_ENABLED", "2FA enabled"
        TWO_FA_DISABLED = "TWO_FA_DISABLED", "2FA disabled"
        ACCOUNT_DELETED = "ACCOUNT_DELETED", "Account deletion requested"
        ACCOUNT_EXPORTED = "ACCOUNT_EXPORTED", "Account data exported"

        # Device
        DEVICE_REGISTERED = "DEVICE_REGISTERED", "Device registered"
        DEVICE_REMOVED = "DEVICE_REMOVED", "Device removed"
        DEVICE_KEY_ROTATED = "DEVICE_KEY_ROTATED", "Device signing key rotated"
        TAMPER_DETECTED = "TAMPER_DETECTED", "Protection interrupted / tamper signal"

        # Policy
        POLICY_CREATED = "POLICY_CREATED", "Policy created"
        POLICY_MODIFIED = "POLICY_MODIFIED", "Policy modified"
        POLICY_MODIFICATION_BLOCKED = "POLICY_MODIFICATION_BLOCKED", "Blocked: weekly plan locked"
        HARD_LOCK_ENABLED = "HARD_LOCK_ENABLED", "Hard lock policy enabled"

        # Unlock
        UNLOCK_REQUESTED = "UNLOCK_REQUESTED", "Unlock requested"
        UNLOCK_APPROVED = "UNLOCK_APPROVED", "Unlock approved"
        UNLOCK_REJECTED = "UNLOCK_REJECTED", "Unlock rejected"
        UNLOCK_TOKEN_ISSUED = "UNLOCK_TOKEN_ISSUED", "Unlock token issued"
        UNLOCK_TOKEN_REDEEMED = "UNLOCK_TOKEN_REDEEMED", "Unlock token redeemed"
        UNLOCK_TOKEN_REPLAY_BLOCKED = "UNLOCK_TOKEN_REPLAY_BLOCKED", "Blocked: token replay attempt"

        # Family / accountability
        FAMILY_MEMBER_ADDED = "FAMILY_MEMBER_ADDED", "Family member added"
        FAMILY_PERMISSION_CHANGED = "FAMILY_PERMISSION_CHANGED", "Family permission changed"

        # Subscription
        SUBSCRIPTION_ACTIVATED = "SUBSCRIPTION_ACTIVATED", "Subscription activated"
        SUBSCRIPTION_CANCELED = "SUBSCRIPTION_CANCELED", "Subscription canceled"
        SUBSCRIPTION_PAYMENT_FAILED = "SUBSCRIPTION_PAYMENT_FAILED", "Subscription payment failed"

        # Anti-abuse
        REFERRAL_FRAUD_SUSPECTED = "REFERRAL_FRAUD_SUSPECTED", "Referral flagged as suspected fraud"
        RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED", "Rate limit exceeded"

    event_type = models.CharField(max_length=64, choices=EventType.choices, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events_caused",
        help_text="Who performed the action. Null for system/celery-initiated events.",
    )
    # Generic-ish target reference kept simple (no contenttypes framework) since we
    # only ever need "what kind of thing, which id" for display — not reverse queries.
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type", "-created_at"]),
            models.Index(fields=["actor", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} by {self.actor_id} @ {self.created_at:%Y-%m-%d %H:%M:%S}"

    def save(self, *args, **kwargs):
        if self.pk:
            existing = type(self).objects.filter(pk=self.pk).first()
            if existing is not None:
                raise ValueError("AuditLog rows are append-only and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AuditLog rows are append-only and cannot be deleted through the ORM.")


def write_audit_log(event_type, actor=None, target=None, metadata=None, ip_address=None):
    """
    Single entry point for writing audit events, so every call site is consistent
    and nobody constructs AuditLog objects ad hoc with slightly different field
    conventions scattered across apps.
    """
    target_type = ""
    target_id = ""
    if target is not None:
        target_type = type(target).__name__
        target_id = str(getattr(target, "pk", ""))

    return AuditLog.objects.create(
        event_type=event_type,
        actor=actor,
        target_type=target_type,
        target_id=target_id,
        metadata=metadata or {},
        ip_address=ip_address,
    )
