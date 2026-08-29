"""
Accounts: the custom User model plus onboarding/consent state.

Design decision (architecture doc §9): onboarding consent is not just a frontend
screen the user clicks through — `OnboardingState` is a real backend record, and
`apps.policies` checks it server-side before allowing any HARD_LOCK policy to be
created. This directly implements blueprint §38's explicit requirement: "قبل أي Lock
قوي يجب وجود: شرح واضح، موافقة واضحة، توضيح الصلاحيات."
"""
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.models import TimestampedModel, UUIDModel


class User(AbstractUser):
    """
    Custom user model from day one (never build on the default — swapping later is
    a real migration, per Django's own well-known guidance).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=80, blank=True)
    avatar_url = models.URLField(blank=True)

    # §39 Guest / Free Trial: a guest converts into a real User record with this flag,
    # rather than being a separate model — this way progress made as a guest carries
    # over cleanly with zero migration, satisfying the "Upgrade / Register" flow.
    is_guest = models.BooleanField(default=False)

    # §41 Privacy Center: soft-delete window rather than immediate hard delete, so
    # "how to delete account" is honest (data really goes away) while still allowing
    # a short undo window and satisfying any applicable legal retention minimums for
    # billing records specifically (handled separately in apps.monetization).
    deletion_requested_at = models.DateTimeField(null=True, blank=True)

    timezone = models.CharField(max_length=64, default="UTC")
    locale = models.CharField(max_length=10, default="en")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        indexes = [models.Index(fields=["email"])]

    def __str__(self):
        return self.email


class OnboardingState(UUIDModel, TimestampedModel):
    """
    §38 Onboarding, implemented as a real gate rather than a UI-only wizard.

    `permissions_explained_at` and `consent_given_at` being non-null is checked by
    apps.policies before ANY policy with enforcement_level=HARD_LOCK can be created —
    see apps.policies.services.assert_hard_lock_allowed(). This is the concrete,
    backend-enforced version of the blueprint's own explicit requirement.
    """

    class Step(models.TextChoices):
        ACCOUNT_CREATED = "ACCOUNT_CREATED", "Account created"
        GOALS_CHOSEN = "GOALS_CHOSEN", "Goals chosen"
        APPS_CHOSEN = "APPS_CHOSEN", "Apps chosen"
        LIMITS_CHOSEN = "LIMITS_CHOSEN", "Limits chosen"
        WEEKLY_LOCK_DECIDED = "WEEKLY_LOCK_DECIDED", "Weekly lock decision made"
        PERMISSIONS_EXPLAINED = "PERMISSIONS_EXPLAINED", "Device permissions explained"
        PERMISSIONS_GRANTED = "PERMISSIONS_GRANTED", "Device permissions granted"
        POLICY_CONFIRMED = "POLICY_CONFIRMED", "Policy confirmed"
        COMPLETE = "COMPLETE", "Onboarding complete"

    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="onboarding_state")
    current_step = models.CharField(max_length=32, choices=Step.choices, default=Step.ACCOUNT_CREATED)

    # These two fields are the actual server-side gate — see docstring above.
    permissions_explained_at = models.DateTimeField(null=True, blank=True)
    consent_given_at = models.DateTimeField(null=True, blank=True)

    completed_at = models.DateTimeField(null=True, blank=True)

    def is_hard_lock_consented(self) -> bool:
        return self.permissions_explained_at is not None and self.consent_given_at is not None


class UserGoal(UUIDModel, TimestampedModel):
    """
    §42/§45 Personal Goals. Multi-select (a user can pick Study + Better Sleep), so
    this is a separate row-per-goal model rather than a single CharField — also lets
    apps.ai_coach's HeuristicLimitRecommender weight recommendations by active goals
    (architecture doc §6) without parsing a packed field.
    """

    class Goal(models.TextChoices):
        STUDY = "STUDY", "🎓 Study"
        CODING = "CODING", "💻 Coding"
        BETTER_SLEEP = "BETTER_SLEEP", "😴 Better Sleep"
        FOCUS = "FOCUS", "🧠 Focus"
        READING = "READING", "📚 Reading"
        DIGITAL_DETOX = "DIGITAL_DETOX", "🌱 Digital Detox"
        PRODUCTIVITY = "PRODUCTIVITY", "Productivity"
        REDUCE_SOCIAL_MEDIA = "REDUCE_SOCIAL_MEDIA", "Reduce Social Media"

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="goals")
    goal = models.CharField(max_length=32, choices=Goal.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "goal"], name="unique_user_goal"),
        ]
