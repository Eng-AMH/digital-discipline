from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import User, OnboardingState, UserGoal


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["email", "username", "display_name", "is_guest", "is_active", "date_joined"]
    list_filter = ["is_guest", "is_active", "is_staff"]
    search_fields = ["email", "username", "display_name"]
    ordering = ["-date_joined"]
    # BaseUserAdmin's fieldsets reference 'username' as USERNAME_FIELD by default;
    # our custom User uses email as USERNAME_FIELD, so fieldsets are overridden
    # rather than inherited as-is to avoid a mismatched admin form.
    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        ("Profile", {"fields": ("display_name", "avatar_url", "timezone", "locale", "is_guest")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Deletion", {"fields": ("deletion_requested_at",)}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "username", "password1", "password2")}),
    )


@admin.register(OnboardingState)
class OnboardingStateAdmin(admin.ModelAdmin):
    list_display = ["user", "current_step", "permissions_explained_at", "consent_given_at", "completed_at"]
    list_filter = ["current_step"]
    search_fields = ["user__email"]


@admin.register(UserGoal)
class UserGoalAdmin(admin.ModelAdmin):
    list_display = ["user", "goal", "is_active"]
    list_filter = ["goal", "is_active"]
