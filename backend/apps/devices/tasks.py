"""
Device Celery tasks. See config/celery.py beat_schedule for cadence.
"""
from celery import shared_task
from django.utils import timezone

STALE_HEARTBEAT_THRESHOLD_MINUTES = 30


@shared_task
def check_stale_heartbeats():
    """
    §9 Anti-Tamper / Device Health. If a device hasn't reported a heartbeat in
    STALE_HEARTBEAT_THRESHOLD_MINUTES, flag it as potentially offline/tampered on
    the dashboard even though the device itself never got to report the state
    change (e.g. it was killed, lost connectivity, or the AccessibilityService was
    force-stopped in a way that skipped the normal lifecycle callback).
    """
    from apps.devices.models import Device
    from apps.notifications.models import Notification, NotificationType
    from apps.core.models import write_audit_log, AuditLog

    threshold = timezone.now() - timezone.timedelta(minutes=STALE_HEARTBEAT_THRESHOLD_MINUTES)
    stale_devices = Device.objects.filter(
        is_active=True, last_heartbeat_at__lt=threshold, platform=Device.Platform.ANDROID
    )

    flagged = 0
    for device in stale_devices:
        write_audit_log(
            AuditLog.EventType.TAMPER_DETECTED,
            actor=device.user,
            target=device,
            metadata={"reason": "stale_heartbeat", "last_heartbeat_at": str(device.last_heartbeat_at)},
        )
        Notification.objects.create(
            user=device.user,
            notification_type=NotificationType.PROTECTION_INTERRUPTED,
            title="Protection interrupted",
            body=f"{device.name} hasn't checked in recently. Enforcement may not be active.",
            metadata={"device_id": str(device.id)},
        )
        flagged += 1

    return {"flagged": flagged}
