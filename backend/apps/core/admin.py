from django.contrib import admin

from apps.core.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only in admin, matching the model's own append-only enforcement
    (AuditLog.save/delete raise ValueError on modification attempts) — the admin
    UI should not even offer an edit form that would fail on submit."""
    list_display = ["event_type", "actor", "target_type", "target_id", "created_at"]
    list_filter = ["event_type", "created_at"]
    search_fields = ["actor__email", "target_id"]
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
