from rest_framework import serializers

from apps.ai_coach.models import AICoachReport


class AICoachReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = AICoachReport
        fields = [
            "period", "period_start", "period_end", "biggest_usage_period",
            "screen_time_change_percent", "most_problematic_app", "narrative_text",
            "recommendation_text", "generated_by", "generated_at",
        ]
        read_only_fields = fields
