from django.contrib import admin

from apps.ai_coach.models import AICoachReport


@admin.register(AICoachReport)
class AICoachReportAdmin(admin.ModelAdmin):
    list_display = ["user", "period", "period_start", "period_end", "generated_by", "generated_at"]
    list_filter = ["period", "generated_by"]
    search_fields = ["user__email"]
