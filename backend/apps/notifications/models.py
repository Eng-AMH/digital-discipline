"""
Notifications: §41 (blueprint's own examples: usage warnings, limit reached,
session completed, streak). §41 Privacy Center explicitly lists "إعدادات
Notifications" as user-controllable — NotificationPreference below is that control.

Delivery is via FCM (Firebase Cloud Messaging) push on Android — the actual FCM
send call is a documented integration point (send_push in services.py) since it
requires a real Firebase project/server key not available in this environment;
the Notification row itself (what WOULD be sent, and to whom) is fully real.
"""
from django.db import models

from apps.core.models import UUIDModel


class NotificationType(models.TextChoices):
    USAGE_ABOVE_USUAL = "USAGE_ABOVE_USUAL", "Usage above usual"
    TIME_REMAINING_WARNING = "TIME_REMAINING_WARNING", "Time remaining warning (10m/5m left)"
    LIMIT_REACHED = "LIMIT_REACHED", "Daily limit reached"
    FOCUS_SESSION_COMPLETED = "FOCUS_SESSION_COMPLETED", "Focus session completed"
    STREAK_MILESTONE = "STREAK_MILESTONE", "Streak milestone"
    UNLOCK_REQUEST_RECEIVED = "UNLOCK_REQUEST_RECEIVED", "Unlock request received (accountability partner)"
    UNLOCK_REQUEST_DECIDED = "UNLOCK_REQUEST_DECIDED", "Unlock request approved/rejected"
    CHALLENGE_INVITE = "CHALLENGE_INVITE", "Challenge invite"
    WEEKLY_AI_REPORT_READY = "WEEKLY_AI_REPORT_READY", "Weekly AI report ready"
    WEEKLY_PLAN_UNLOCKED = "WEEKLY_PLAN_UNLOCKED", "Weekly plan lock expired"
    PROTECTION_INTERRUPTED = "PROTECTION_INTERRUPTED", "Protection interrupted (tamper signal)"
    SUBSCRIPTION_PAYMENT_FAILED = "SUBSCRIPTION_PAYMENT_FAILED", "Subscription payment failed"


class Notification(UUIDModel):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="notifications")
    notification_type = models.CharField(max_length=32, choices=NotificationType.choices)
    title = models.CharField(max_length=100)
    body = models.CharField(max_length=280)
    metadata = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "is_read", "-created_at"])]


class NotificationPreference(UUIDModel):
    """One row per (user, notification_type) — absence of a row means 'enabled'
    (opt-out model), so newly added notification types default ON without a
    migration having to backfill preference rows for every existing user."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="notification_preferences")
    notification_type = models.CharField(max_length=32, choices=NotificationType.choices)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "notification_type"], name="unique_user_notif_pref"),
        ]
