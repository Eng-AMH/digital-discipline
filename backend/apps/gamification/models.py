"""
Gamification: §16 Gamification/Focus Score, §17 Streaks, §18 Focus Tokens,
§43 Achievements.

Design decision (architecture doc §4, §8): TokenTransaction is a ledger, not a
balance field on User. `balance = SUM(amount)` is always computed, never directly
writable — this is what makes §39's anti-abuse auditing possible (you can see
exactly which action granted which tokens) and prevents an entire class of bugs
where a balance field silently drifts from what actually happened.

Design decision: FocusScoreSnapshot is a time-series (one row per day per user),
not an overwritten "current_score" field — required for §27 Focus League history
and §16 trend charts ("compare to last week").
"""
from django.db import models

from apps.core.models import TimestampedModel, UUIDModel


class FocusScoreSnapshot(UUIDModel):
    """
    §19 Focus Score. Computed nightly by Celery task
    apps.gamification.tasks.compute_focus_scores using the exact formula documented
    in architecture doc §8 (kept as named constants in
    apps.gamification.scoring, not inlined here, so the formula has one home).
    """

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="focus_score_snapshots")
    date = models.DateField(db_index=True)
    score = models.PositiveSmallIntegerField(help_text="0-100")

    # Component breakdown stored alongside the total — lets the dashboard explain
    # WHY the score is what it is ("you lost points on night usage"), not just show
    # a number, and lets the formula be audited/tuned without recomputing history.
    limit_adherence_component = models.FloatField()
    focus_completion_component = models.FloatField()
    consistency_component = models.FloatField()
    night_usage_component = models.FloatField()
    weekly_plan_component = models.FloatField()

    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "date"], name="unique_user_score_per_day"),
        ]
        indexes = [models.Index(fields=["user", "-date"])]


class Streak(UUIDModel, TimestampedModel):
    """§17 Streaks. One row per user (current + best), updated by the same nightly
    Celery job that computes FocusScoreSnapshot — a day "counts" toward the streak
    if that day's FocusScoreSnapshot exceeds STREAK_MIN_SCORE (see scoring.py)."""

    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="streak")
    current_streak_days = models.PositiveIntegerField(default=0)
    best_streak_days = models.PositiveIntegerField(default=0)
    last_counted_date = models.DateField(null=True, blank=True)


class TokenTransaction(UUIDModel):
    """
    §18 Focus Tokens ledger. See module docstring — this IS the balance, via
    SUM(amount) where positive=earn, negative=spend. Never mutate a balance field.
    """

    class Reason(models.TextChoices):
        STREAK_MILESTONE = "STREAK_MILESTONE", "Streak milestone"
        FOCUS_SESSION_COMPLETED = "FOCUS_SESSION_COMPLETED", "Focus session completed"
        CHALLENGE_COMPLETED = "CHALLENGE_COMPLETED", "Challenge completed"
        REFERRAL_REWARD = "REFERRAL_REWARD", "Referral reward"
        REWARDED_AD = "REWARDED_AD", "Rewarded ad watched"
        ACHIEVEMENT_UNLOCKED = "ACHIEVEMENT_UNLOCKED", "Achievement unlocked"
        EARN_YOUR_SCROLL = "EARN_YOUR_SCROLL", "Earn Your Scroll (§28)"
        SPENT_EXTRA_TIME = "SPENT_EXTRA_TIME", "Spent on extra time unlock"
        SPENT_STORE_PURCHASE = "SPENT_STORE_PURCHASE", "Spent in cosmetic store"
        ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT", "Manual adjustment"

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="token_transactions")
    amount = models.IntegerField(help_text="Positive=earn, negative=spend")
    reason = models.CharField(max_length=32, choices=Reason.choices)
    reference_id = models.CharField(
        max_length=64, blank=True, help_text="e.g. FocusSession id, Challenge id — free text, not FK, "
                                              "so this ledger never blocks deletion of the source object"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "-created_at"])]


class Achievement(UUIDModel):
    """§43 Achievements catalog — the definitions, not the unlocks."""

    key = models.SlugField(unique=True, help_text="e.g. 'first_focus_session', '30_day_streak'")
    title = models.CharField(max_length=100)
    description = models.CharField(max_length=280)
    icon = models.CharField(max_length=50, blank=True)
    token_reward = models.PositiveIntegerField(default=0)


class UserAchievement(UUIDModel):
    """Per-user unlocked achievements. Rule evaluation happens in
    apps.gamification.tasks.evaluate_achievements (Celery, per architecture §2)."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="achievements")
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE, related_name="unlocks")
    unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "achievement"], name="unique_user_achievement"),
        ]
