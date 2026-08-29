from rest_framework import serializers

from apps.devices.models import Device, ActivityLog, DeviceEvent


class DeviceRegisterSerializer(serializers.ModelSerializer):
    """
    §11 Device-Specific Unlock System registration. The client sends ONLY its
    Ed25519 PUBLIC key (generated on-device, Android Keystore) — see architecture
    doc §5.2. This is the literal enforcement point of "لا نخزن الـ Secret الخام."
    """

    class Meta:
        model = Device
        fields = ["id", "platform", "enrollment_type", "name", "model_name", "os_version", "app_version", "public_key"]
        read_only_fields = ["id"]


class DeviceSerializer(serializers.ModelSerializer):
    is_healthy = serializers.BooleanField(read_only=True)

    class Meta:
        model = Device
        fields = [
            "id", "platform", "enrollment_type", "name", "model_name", "os_version", "app_version",
            "is_active", "last_heartbeat_at", "accessibility_service_active",
            "vpn_service_active", "usage_access_granted", "is_healthy", "created_at",
        ]
        read_only_fields = fields


class HeartbeatSerializer(serializers.Serializer):
    """
    §9 Device Health heartbeat payload. Signed by the device's private key —
    verified server-side against the stored public key before being trusted (see
    views.py DeviceHeartbeatView), per architecture doc §5.2's "every subsequent
    sensitive device action is signed by the device's private key" model.
    """
    accessibility_service_active = serializers.BooleanField()
    vpn_service_active = serializers.BooleanField()
    usage_access_granted = serializers.BooleanField()
    signature = serializers.CharField(help_text="Base64 Ed25519 signature of the other fields, canonically encoded")


class ActivityLogBatchItemSerializer(serializers.Serializer):
    """One entry in a batch sync — devices accumulate these offline (Room DB) and
    upload in bulk, per architecture doc §5.4 offline-first design."""
    target_type = serializers.ChoiceField(choices=ActivityLog.TargetType.choices)
    target_identifier = serializers.CharField(max_length=255)
    occurred_date = serializers.DateField()
    minutes_used = serializers.IntegerField(min_value=0)
    session_started_at = serializers.DateTimeField()
    session_ended_at = serializers.DateTimeField()


class ActivityLogBatchSerializer(serializers.Serializer):
    entries = ActivityLogBatchItemSerializer(many=True)


class DeviceEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceEvent
        fields = ["event_type", "metadata", "occurred_at"]
