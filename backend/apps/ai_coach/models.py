"""
AI Coach: §17 AI Coach, §18 Smart Limits.

Design decision (architecture doc §6): these are two genuinely different things the
blueprint both calls "AI" — kept as separate models/services so neither is
misrepresented as the other:
  - AICoachReport (this file) = real NLG task, backed by AICoachProvider interface
    in services.py (provider-agnostic, MockAICoachProvider ships since no LLM API
    key was supplied — see services.py docstring).
  - Smart Limit recommendations (§18) = a deterministic heuristic, NOT stored as
    its own model since it's computed on-demand from ActivityLog — see
    apps.ai_coach.recommender.HeuristicLimitRecommender. Explicitly not called "AI"
    anywhere in code/docs, because it isn't one.
"""
from django.db import models

from apps.core.models import UUIDModel


class AICoachReport(UUIDModel):
    """§17 weekly AI Coach narrative report."""

    class Period(models.TextChoices):
        WEEKLY = "WEEKLY", "Weekly"
        DAILY_INSIGHT = "DAILY_INSIGHT", "Daily insight"

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="ai_coach_reports")
    period = models.CharField(max_length=16, choices=Period.choices, default=Period.WEEKLY)
    period_start = models.DateField()
    period_end = models.DateField()

    # Structured fields the frontend can render directly (best_day, worst_period,
    # etc. — matching the blueprint's own listed report contents in §17) PLUS the
    # free-text narrative, so a report is never "just a blob of AI text" with no
    # structure to build UI against.
    biggest_usage_period = models.CharField(max_length=100, blank=True)
    screen_time_change_percent = models.FloatField(null=True, blank=True)
    most_problematic_app = models.CharField(max_length=100, blank=True)
    narrative_text = models.TextField()
    recommendation_text = models.TextField(blank=True)

    generated_by = models.CharField(
        max_length=50, default="mock",
        help_text="Which AICoachProvider implementation generated this — 'mock' is honestly "
                   "labeled when no LLM provider is configured, never silently swapped for real text.",
    )
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "period", "period_start"], name="unique_user_report_per_period"),
        ]
