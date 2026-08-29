from rest_framework import serializers

from apps.policies.models import (
    AppLimit, WebsiteLimit, WeeklyPlan, Schedule, FocusSession, UnlockRequest, UnlockToken,
)


class AppLimitSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppLimit
        fields = ["id", "package_name", "display_name", "daily_minutes", "is_enabled", "created_at"]
        read_only_fields = ["id", "created_at"]


class WebsiteLimitSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebsiteLimit
        fields = ["id", "domain", "category", "daily_minutes", "is_enabled", "created_at"]
        read_only_fields = ["id", "created_at"]


class WeeklyPlanSerializer(serializers.ModelSerializer):
    is_currently_locked = serializers.SerializerMethodField()

    class Meta:
        model = WeeklyPlan
        fields = [
            "id", "plan_type", "app_limits", "website_limits", "is_confirmed",
            "confirmed_at", "locked_until", "is_hard_locked", "is_currently_locked",
        ]
        read_only_fields = ["id", "confirmed_at", "locked_until", "is_currently_locked"]

    def get_is_currently_locked(self, obj) -> bool:
        return obj.is_currently_locked()


class ScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Schedule
        fields = [
            "id", "mode", "label", "start_time", "end_time", "days_of_week",
            "is_enabled", "blocked_packages", "allowed_packages",
        ]
        read_only_fields = ["id"]


class FocusSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FocusSession
        fields = [
            "id", "device", "session_type", "planned_minutes", "allowed_packages",
            "blocked_packages", "status", "started_at", "ended_at", "actual_minutes",
        ]
        read_only_fields = ["id", "status", "started_at", "ended_at", "actual_minutes"]


class UnlockRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnlockRequest
        fields = [
            "id", "device", "package_name", "requested_minutes", "reason_type",
            "reason_note", "status", "approver", "decided_at", "created_at",
        ]
        read_only_fields = ["id", "status", "approver", "decided_at", "created_at"]


class UnlockTokenSerializer(serializers.ModelSerializer):
    """
    Returned to the device after an UnlockRequest is approved. `payload` +
    `signature` are exactly what the device verifies against the server's public
    key (architecture doc §5.3) before applying the grant locally.
    """

    class Meta:
        model = UnlockToken
        fields = ["id", "package_name", "granted_minutes", "payload", "signature", "issued_at", "expires_at", "redeemed_at"]
        read_only_fields = fields
