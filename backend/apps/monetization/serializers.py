from rest_framework import serializers

from apps.monetization.models import Plan, Subscription, ReferralCode, Referral, StoreItem


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "tier", "display_name", "monthly_price_cents", "max_devices",
            "max_daily_limit_minutes", "weekly_lock_available", "focus_mode_available",
            "sleep_mode_available", "ai_coach_available", "ads_enabled", "family_features_available",
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = ["id", "plan", "status", "source", "current_period_start", "current_period_end", "canceled_at"]
        read_only_fields = fields


class ReferralCodeSerializer(serializers.ModelSerializer):
    referral_link = serializers.SerializerMethodField()

    class Meta:
        model = ReferralCode
        fields = ["code", "referral_link"]
        read_only_fields = fields

    def get_referral_link(self, obj) -> str:
        # Matches blueprint's own example format: focus.app/r/AMMAR123
        return f"https://kerno.app/r/{obj.code}"


class ReferralSerializer(serializers.ModelSerializer):
    referred_display_name = serializers.CharField(source="referred_user.display_name", read_only=True)

    class Meta:
        model = Referral
        fields = ["id", "referred_display_name", "status", "qualified_at", "reward_granted_days", "created_at"]
        read_only_fields = fields


class StoreItemSerializer(serializers.ModelSerializer):
    owned = serializers.SerializerMethodField()

    class Meta:
        model = StoreItem
        fields = ["id", "category", "name", "description", "token_price", "real_money_price_cents", "requires_plan_tier", "owned"]
        read_only_fields = fields

    def get_owned(self, obj) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.owners.filter(user=request.user).exists()
