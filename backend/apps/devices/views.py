from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.models import write_audit_log, AuditLog
from apps.devices.models import Device, ActivityLog, DeviceEvent
from apps.devices.serializers import (
    DeviceRegisterSerializer, DeviceSerializer, HeartbeatSerializer,
    ActivityLogBatchSerializer, DeviceEventSerializer,
)
from apps.devices.services import record_heartbeat
from apps.monetization.entitlements import resolve_entitlements
from apps.policies.services import server_public_key_b64


class ServerPublicKeyView(APIView):
    """
    §5.3: the server's Ed25519 public key, pinned by the app at registration time
    so it can verify server-signed unlock tokens and offline policy blobs without
    a network round-trip on every check. No auth required — this is a public key
    by definition.
    """
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        return Response({"server_public_key": server_public_key_b64()})


class DeviceRegisterView(generics.CreateAPIView):
    """
    §48 Multi-Device: enforces max_devices from EntitlementResolver (architecture
    §7) — this is the ACTUAL enforcement point for §21/§24's device-count limits
    per plan tier, not just documentation of the limit.
    """
    serializer_class = DeviceRegisterSerializer

    def create(self, request, *args, **kwargs):
        entitlements = resolve_entitlements(request.user)
        current_count = Device.objects.filter(user=request.user, is_active=True).count()
        if current_count >= entitlements.max_devices:
            return Response(
                {
                    "detail": f"Your plan ({entitlements.plan_tier}) allows up to "
                              f"{entitlements.max_devices} device(s). Upgrade to add more."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = serializer.save(user=request.user)

        DeviceEvent.objects.create(device=device, event_type=DeviceEvent.EventType.REGISTERED, occurred_at=device.created_at)
        write_audit_log(AuditLog.EventType.DEVICE_REGISTERED, actor=request.user, target=device)

        return Response(DeviceSerializer(device).data, status=status.HTTP_201_CREATED)


class DeviceListView(generics.ListAPIView):
    serializer_class = DeviceSerializer

    def get_queryset(self):
        return Device.objects.filter(user=self.request.user, is_active=True)


class DeviceRemoveView(APIView):
    """
    §40 Backup & Recovery: removing a device does NOT delete the user's policies
    (AppLimit/WeeklyPlan/etc. all FK to User, never Device — see apps.policies
    module docstring) — only this binding record and its device-scoped telemetry.
    Re-registering a new device automatically re-syncs the full policy set via
    build_signed_policy_blob, with zero special-case "restore" logic needed.
    """

    def delete(self, request, device_id):
        device = get_object_or_404(Device, id=device_id, user=request.user)
        device.is_active = False
        device.save(update_fields=["is_active"])
        write_audit_log(AuditLog.EventType.DEVICE_REMOVED, actor=request.user, target=device)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeviceHeartbeatView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "device_heartbeat"

    def post(self, request, device_id):
        device = get_object_or_404(Device, id=device_id, user=request.user, is_active=True)
        serializer = HeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        updated_device, error = record_heartbeat(device=device, **serializer.validated_data)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        return Response(DeviceSerializer(updated_device).data)


class ActivityLogBatchSyncView(APIView):
    """
    §43 Offline Mode: devices batch ActivityLog entries locally (Room DB) and
    upload in bulk on reconnect — this endpoint is the sync target. Idempotency
    note: duplicate entries from a retried sync are tolerated (not deduplicated
    at the DB level via a unique constraint) because minutes-used aggregation
    happens at query time over date ranges in apps.gamification.scoring and
    apps.ai_coach.tasks — a real production hardening step would add a
    client-generated idempotency key per entry, flagged here rather than silently
    assumed solved.
    """

    def post(self, request, device_id):
        device = get_object_or_404(Device, id=device_id, user=request.user, is_active=True)
        serializer = ActivityLogBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        entries = serializer.validated_data["entries"]
        created = ActivityLog.objects.bulk_create([
            ActivityLog(device=device, user=request.user, **entry) for entry in entries
        ])
        return Response({"synced_count": len(created)}, status=status.HTTP_201_CREATED)


class DeviceEventBatchSyncView(APIView):
    def post(self, request, device_id):
        device = get_object_or_404(Device, id=device_id, user=request.user, is_active=True)
        events_data = request.data.get("events", [])
        serializer = DeviceEventSerializer(data=events_data, many=True)
        serializer.is_valid(raise_exception=True)
        created = DeviceEvent.objects.bulk_create([
            DeviceEvent(device=device, **event) for event in serializer.validated_data
        ])
        return Response({"synced_count": len(created)}, status=status.HTTP_201_CREATED)
