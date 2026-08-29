"""
Accounts serializers. Registration is deliberately its own serializer (not a
generic ModelSerializer on User) since it needs password confirmation + hashing,
which read/write user-profile serializers should never handle.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.accounts.models import OnboardingState, UserGoal

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["email", "username", "display_name", "password", "password_confirm"]

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        # §38 Onboarding: every new user gets a real OnboardingState row at
        # ACCOUNT_CREATED — this is what apps.policies.services.assert_hard_lock_allowed
        # checks against later, so it must exist from the first moment, not be
        # lazily created on first policy request.
        OnboardingState.objects.create(user=user)
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "username", "display_name", "avatar_url", "timezone", "locale", "is_guest", "date_joined"]
        read_only_fields = ["id", "email", "is_guest", "date_joined"]


class OnboardingStateSerializer(serializers.ModelSerializer):
    is_hard_lock_consented = serializers.SerializerMethodField()

    class Meta:
        model = OnboardingState
        fields = [
            "current_step", "permissions_explained_at", "consent_given_at",
            "completed_at", "is_hard_lock_consented",
        ]
        read_only_fields = ["permissions_explained_at", "consent_given_at", "completed_at"]

    def get_is_hard_lock_consented(self, obj) -> bool:
        return obj.is_hard_lock_consented()


class UserGoalSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserGoal
        fields = ["id", "goal", "is_active"]
        read_only_fields = ["id"]
