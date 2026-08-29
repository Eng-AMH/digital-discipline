from rest_framework import serializers

from apps.gamification.models import FocusScoreSnapshot, Streak, TokenTransaction, Achievement, UserAchievement


class FocusScoreSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = FocusScoreSnapshot
        fields = [
            "date", "score", "limit_adherence_component", "focus_completion_component",
            "consistency_component", "night_usage_component", "weekly_plan_component",
        ]


class StreakSerializer(serializers.ModelSerializer):
    class Meta:
        model = Streak
        fields = ["current_streak_days", "best_streak_days", "last_counted_date"]


class TokenTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TokenTransaction
        fields = ["id", "amount", "reason", "reference_id", "created_at"]
        read_only_fields = fields


class AchievementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Achievement
        fields = ["id", "key", "title", "description", "icon", "token_reward"]


class UserAchievementSerializer(serializers.ModelSerializer):
    achievement = AchievementSerializer(read_only=True)

    class Meta:
        model = UserAchievement
        fields = ["achievement", "unlocked_at"]
