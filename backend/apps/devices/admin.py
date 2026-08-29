from django.contrib import admin

from apps.devices.models import Device, DeviceEvent, ActivityLog


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "platform", "enrollment_type", "is_active", "is_healthy", "last_heartbeat_at"]
    list_filter = ["platform", "enrollment_type", "is_active"]
    search_fields = ["name", "user__email", "public_key"]
    readonly_fields = ["public_key", "created_at", "updated_at"]


@admin.register(DeviceEvent)
class DeviceEventAdmin(admin.ModelAdmin):
    list_display = ["device", "event_type", "occurred_at", "received_at"]
    list_filter = ["event_type"]


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ["user", "target_type", "target_identifier", "occurred_date", "minutes_used"]
    list_filter = ["target_type", "occurred_date"]
    search_fields = ["user__email", "target_identifier"]
