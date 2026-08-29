"""
Notification dispatch. §44's actual delivery mechanism on Android is FCM (Firebase
Cloud Messaging) push — `send_push` below is the integration point, honestly
documented: it requires a real Firebase project + server key
(settings.FCM_SERVER_KEY) not available in this build environment. The
Notification DATABASE ROW (what would be sent, to whom, with what content) is
fully real regardless — this function only covers the actual network push.
"""
import logging

logger = logging.getLogger(__name__)


def send_push(notification):
    """
    Called after a Notification row is created, wherever that happens across the
    codebase (apps.devices.services, apps.policies.views, Celery tasks, etc.).
    Checks the user's NotificationPreference first — respecting §41's
    "إعدادات Notifications" opt-out is not optional.
    """
    from django.conf import settings
    from apps.notifications.models import NotificationPreference

    pref = NotificationPreference.objects.filter(
        user=notification.user, notification_type=notification.notification_type
    ).first()
    if pref is not None and not pref.is_enabled:
        return  # user has explicitly opted out of this notification type

    if not settings.FCM_SERVER_KEY:
        logger.info(
            "FCM_SERVER_KEY not configured — notification %s created in DB but not pushed. "
            "See apps.notifications.services module docstring.",
            notification.id,
        )
        return

    # Real implementation would POST to FCM's send endpoint with the device's
    # registration token(s) (would need a DeviceFCMToken model, not yet added
    # since it has no purpose until a real Firebase project exists) and
    # settings.FCM_SERVER_KEY as the Authorization header. Left undone here
    # rather than fabricated, per the same honesty principle as the payment
    # webhooks in apps.monetization.views.
    logger.warning("send_push: FCM integration not implemented in this build.")
