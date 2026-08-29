from rest_framework import serializers

from apps.social.models import (
    FriendRequest, AccountabilityLink, Challenge, ChallengeMember, League, FamilyGroup, FamilyMember,
)


class FriendRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = FriendRequest
        fields = ["id", "from_user", "to_user", "status", "created_at"]
        read_only_fields = ["id", "from_user", "status", "created_at"]


class AccountabilityLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountabilityLink
        fields = ["id", "user", "partner", "status", "created_at"]
        read_only_fields = ["id", "user", "status", "created_at"]


class ChallengeMemberSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source="user.display_name", read_only=True)
    # §23: "كل شخص يرى: Focus Score, Streak, Screen Time, Challenge Progress" —
    # these are READ from the member's own gamification rows at serialization
    # time (see ChallengeDetailView), not duplicated fields on this model, per
    # the module docstring's single-source-of-truth decision.
    current_focus_score = serializers.SerializerMethodField()
    current_streak = serializers.SerializerMethodField()

    class Meta:
        model = ChallengeMember
        fields = ["user", "display_name", "joined_at", "completed_at", "current_focus_score", "current_streak"]
        read_only_fields = fields

    def get_current_focus_score(self, obj) -> int | None:
        from apps.gamification.models import FocusScoreSnapshot
        latest = FocusScoreSnapshot.objects.filter(user=obj.user).order_by("-date").first()
        return latest.score if latest else None

    def get_current_streak(self, obj) -> int:
        from apps.gamification.models import Streak
        streak = Streak.objects.filter(user=obj.user).first()
        return streak.current_streak_days if streak else 0


class ChallengeSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    end_date = serializers.DateField(read_only=True)

    class Meta:
        model = Challenge
        fields = ["id", "created_by", "title", "description", "duration_days", "start_date", "end_date", "status", "token_reward", "member_count"]
        read_only_fields = ["id", "created_by", "status", "member_count", "end_date"]

    def get_member_count(self, obj) -> int:
        return obj.members.count()


class LeagueEntrySerializer(serializers.Serializer):
    """Not a ModelSerializer — a League's leaderboard is a computed READ MODEL
    over FocusScoreSnapshot (per module docstring), not a stored row per entry."""
    user_id = serializers.UUIDField()
    display_name = serializers.CharField()
    score = serializers.IntegerField()
    rank = serializers.IntegerField()


class FamilyGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = FamilyGroup
        fields = ["id", "name", "created_by", "created_at"]
        read_only_fields = ["id", "created_by", "created_at"]


class FamilyMemberSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source="user.display_name", read_only=True)

    class Meta:
        model = FamilyMember
        fields = ["id", "user", "display_name", "role", "detailed_activity_visible_to_guardians"]
        read_only_fields = ["id"]
