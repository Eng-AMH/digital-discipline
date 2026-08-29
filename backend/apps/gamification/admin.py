from django.contrib import admin

from apps.gamification.models import FocusScoreSnapshot, Streak, TokenTransaction, Achievement, UserAchievement


@admin.register(FocusScoreSnapshot)
class FocusScoreSnapshotAdmin(admin.ModelAdmin):
    list_display = ["user", "date", "score"]
    list_filter = ["date"]
    search_fields = ["user__email"]


@admin.register(Streak)
class StreakAdmin(admin.ModelAdmin):
    list_display = ["user", "current_streak_days", "best_streak_days", "last_counted_date"]


@admin.register(TokenTransaction)
class TokenTransactionAdmin(admin.ModelAdmin):
    """Read-only: this is a ledger (architecture doc §4/§8) — editing a
    transaction after the fact would corrupt the audit trail the ledger design
    exists to provide."""
    list_display = ["user", "amount", "reason", "reference_id", "created_at"]
    list_filter = ["reason"]
    search_fields = ["user__email"]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ["key", "title", "token_reward"]


@admin.register(UserAchievement)
class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ["user", "achievement", "unlocked_at"]
