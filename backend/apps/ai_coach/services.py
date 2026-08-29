"""
AICoachProvider — provider-agnostic interface for §17's weekly narrative report.

IMPORTANT HONESTY NOTE (architecture doc §6): No LLM API key was provided for this
build. `MockAICoachProvider` below generates the report using a deterministic
template over real structured data (real numbers, real narrative STRUCTURE) — it is
NOT calling any LLM. This is labeled explicitly (AICoachReport.generated_by="mock")
rather than presented as if it were the real feature. Swapping in a real provider
(OpenAI/Anthropic/etc.) later is a matter of implementing `AnthropicAICoachProvider`
against the same `generate_weekly_report` interface and changing
settings.AI_COACH_PROVIDER — no call site changes.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class WeeklyReportInputs:
    """Structured analytics handed to whichever provider generates the narrative —
    the SAME inputs regardless of mock vs real provider, so behavior is comparable."""
    user_display_name: str
    total_screen_time_minutes: int
    prior_week_screen_time_minutes: int
    social_media_minutes: int
    biggest_usage_window: str  # e.g. "9 PM – 11 PM"
    most_used_app: str
    most_problematic_app: str
    blocked_attempts: int
    limits_respected_percent: float
    time_saved_minutes: int
    focus_sessions_completed: int
    active_goals: list[str]


class AICoachProvider(ABC):
    @abstractmethod
    def generate_weekly_report(self, inputs: WeeklyReportInputs) -> dict:
        """Must return a dict with keys: narrative_text, recommendation_text,
        biggest_usage_period, screen_time_change_percent, most_problematic_app."""
        raise NotImplementedError


class MockAICoachProvider(AICoachProvider):
    """
    Deterministic, template-based. Real numbers, templated prose. This is the
    DEVELOPMENT FALLBACK explicitly — see module docstring. Ships as the default
    via settings.AI_COACH_PROVIDER='mock' because no LLM credentials exist in this
    environment.
    """

    def generate_weekly_report(self, inputs: WeeklyReportInputs) -> dict:
        if inputs.prior_week_screen_time_minutes > 0:
            change_percent = round(
                100
                * (inputs.total_screen_time_minutes - inputs.prior_week_screen_time_minutes)
                / inputs.prior_week_screen_time_minutes,
                1,
            )
        else:
            change_percent = 0.0

        direction = "decreased" if change_percent < 0 else "increased"
        change_line = (
            f"Your screen time {direction} by {abs(change_percent):.0f}% compared to last week."
            if inputs.prior_week_screen_time_minutes > 0
            else "This is your first week of tracked data — next week we'll be able to show a trend."
        )

        goal_line = ""
        if inputs.active_goals:
            goal_line = f" Given your goal of {inputs.active_goals[0].replace('_', ' ').lower()}, "

        narrative = (
            f"Your biggest usage period this week was {inputs.biggest_usage_window}. "
            f"{change_line} "
            f"{inputs.most_used_app} was your most-used app, and {inputs.most_problematic_app} "
            f"triggered the most blocked attempts ({inputs.blocked_attempts} this week). "
            f"You respected your limits {inputs.limits_respected_percent:.0f}% of the time and "
            f"saved an estimated {inputs.time_saved_minutes // 60}h {inputs.time_saved_minutes % 60}m "
            f"of screen time."
        )

        recommendation = (
            f"{goal_line}try a {45}-minute Focus Session tomorrow during "
            f"{inputs.biggest_usage_window.split('–')[0].strip()} — that's when you're most likely to drift."
        )

        return {
            "narrative_text": narrative,
            "recommendation_text": recommendation,
            "biggest_usage_period": inputs.biggest_usage_window,
            "screen_time_change_percent": change_percent,
            "most_problematic_app": inputs.most_problematic_app,
        }


def get_ai_coach_provider() -> AICoachProvider:
    from django.conf import settings

    provider_name = getattr(settings, "AI_COACH_PROVIDER", "mock")
    if provider_name == "mock":
        return MockAICoachProvider()
    raise NotImplementedError(
        f"AI_COACH_PROVIDER='{provider_name}' is not implemented. Only 'mock' ships in this build "
        f"(architecture doc §6 — no LLM credentials were provided). Implement a new AICoachProvider "
        f"subclass and register it here to add a real provider."
    )
