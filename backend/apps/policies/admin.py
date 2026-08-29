from django.contrib import admin

from apps.policies.models import (
    AppLimit, WebsiteLimit, WeeklyPlan, Schedule, FocusSession, UnlockRequest, UnlockToken,
)


@admin.register(AppLimit)
class AppLimitAdmin(admin.ModelAdmin):
    list_display = ["user", "display_name", "package_name", "daily_minutes", "is_enabled"]
    search_fields = ["user__email", "package_name", "display_name"]


@admin.register(WebsiteLimit)
class WebsiteLimitAdmin(admin.ModelAdmin):
    list_display = ["user", "domain", "category", "daily_minutes", "is_enabled"]
    list_filter = ["category"]


@admin.register(WeeklyPlan)
class WeeklyPlanAdmin(admin.ModelAdmin):
    list_display = ["user", "plan_type", "is_confirmed", "is_hard_locked", "locked_until"]
    list_filter = ["plan_type", "is_confirmed", "is_hard_locked"]


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ["user", "mode", "label", "start_time", "end_time", "is_enabled"]
    list_filter = ["mode", "is_enabled"]


@admin.register(FocusSession)
class FocusSessionAdmin(admin.ModelAdmin):
    list_display = ["user", "session_type", "status", "planned_minutes", "actual_minutes", "started_at"]
    list_filter = ["session_type", "status"]


@admin.register(UnlockRequest)
class UnlockRequestAdmin(admin.ModelAdmin):
    list_display = ["user", "package_name", "requested_minutes", "reason_type", "status", "approver", "created_at"]
    list_filter = ["reason_type", "status"]
    search_fields = ["user__email", "package_name"]


@admin.register(UnlockToken)
class UnlockTokenAdmin(admin.ModelAdmin):
    """Read-only-ish: signature/payload should never be hand-edited in admin —
    they're cryptographically bound together and editing one without the other
    would just make the token fail verification, silently."""
    list_display = ["device", "package_name", "granted_minutes", "issued_at", "expires_at", "redeemed_at"]
    readonly_fields = ["payload", "signature", "nonce", "issued_at"]

    def has_add_permission(self, request):
        return False  # tokens are only ever minted via apps.policies.services.mint_unlock_token
