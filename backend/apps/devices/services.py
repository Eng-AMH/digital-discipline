"""
Device services. Heartbeat verification is the concrete point where architecture
doc §5.2's device-identity model actually gets exercised on every check-in: the
device signs its own health payload, the server verifies against the stored
public key before trusting any of it, and only THEN updates Device state and
pushes the live update over Channels.
"""
from django.utils import timezone

from apps.core.models import write_audit_log, AuditLog
from apps.policies.services import verify_device_signature


def record_heartbeat(*, device, accessibility_service_active, vpn_service_active, usage_access_granted, signature):
    """
    Verifies the heartbeat is genuinely signed by THIS device's private key before
    trusting any of the reported booleans — an unsigned or wrongly-signed
    heartbeat is rejected outright rather than silently accepted, since accepting
    an unverified "everything is fine" heartbeat would defeat the entire point of
    §9 Anti-Tamper.
    """
    payload = {
        "accessibility_service_active": accessibility_service_active,
        "vpn_service_active": vpn_service_active,
        "usage_access_granted": usage_access_granted,
    }
    if not verify_device_signature(device.public_key, payload, signature):
        write_audit_log(
            AuditLog.EventType.TAMPER_DETECTED,
            actor=device.user,
            target=device,
            metadata={"reason": "heartbeat_signature_invalid"},
        )
        return None, "invalid_signature"

    was_healthy = device.is_healthy
    device.accessibility_service_active = accessibility_service_active
    device.vpn_service_active = vpn_service_active
    device.usage_access_granted = usage_access_granted
    device.last_heartbeat_at = timezone.now()
    device.save()

    is_healthy_now = device.is_healthy
    if was_healthy and not is_healthy_now:
        write_audit_log(
            AuditLog.EventType.TAMPER_DETECTED,
            actor=device.user,
            target=device,
            metadata={"reason": "protection_disabled", **payload},
        )
        from apps.notifications.models import Notification, NotificationType
        Notification.objects.create(
            user=device.user,
            notification_type=NotificationType.PROTECTION_INTERRUPTED,
            title="Protection interrupted",
            body=f"A protection component on {device.name} was turned off.",
            metadata={"device_id": str(device.id)},
        )

    _push_device_health_update(device)
    return device, None


def _push_device_health_update(device):
    """Real-time push over the DeviceHealthConsumer group — architecture doc §12's
    deliberately-scoped Channels use case. Import-local to avoid a hard dependency
    on channels being configured in contexts (e.g. management commands) where it
    isn't needed."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            f"device_health_user_{device.user_id}",
            {
                "type": "device_health_update",
                "payload": {
                    "device_id": str(device.id),
                    "is_healthy": device.is_healthy,
                    "accessibility_service_active": device.accessibility_service_active,
                    "vpn_service_active": device.vpn_service_active,
                    "usage_access_granted": device.usage_access_granted,
                    "last_heartbeat_at": device.last_heartbeat_at.isoformat() if device.last_heartbeat_at else None,
                },
            },
        )
    except Exception:
        # Real-time push is a UX enhancement, not a correctness requirement — the
        # device's health state is already durably saved above regardless of
        # whether the push succeeds, so a Channels/Redis hiccup here must never
        # fail the heartbeat request itself.
        pass
