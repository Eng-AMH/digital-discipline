"""
HeuristicLimitRecommender — §18 Smart Limits.

Architecture doc §6 is explicit: this is a DETERMINISTIC HEURISTIC, not a machine
learning model. Calling it "AI" anywhere in code, docs, or product copy would be
dishonest — it's a percentile calculation over the user's own usage history, mildly
nudged by their stated UserGoal(s). Kept in a separate module/class from
apps.ai_coach.services (the genuine NLG task) specifically so this distinction is
structural, not just a comment someone can miss.
"""
from dataclasses import dataclass
from datetime import timedelta
from statistics import median

TRAILING_WINDOW_DAYS = 14

# If the user has an active goal that plausibly relates to reducing a given app's
# usage, nudge the recommendation down by this fraction. Deliberately small and
# named, not hidden in arithmetic — this is a real product tuning knob.
GOAL_NUDGE_FRACTION = 0.10

GOAL_RELATED_TO_REDUCTION = {"REDUCE_SOCIAL_MEDIA", "DIGITAL_DETOX", "FOCUS", "BETTER_SLEEP"}


@dataclass
class LimitRecommendation:
    package_name: str
    recommended_daily_minutes: int
    based_on_days: int
    rationale: str


class HeuristicLimitRecommender:
    def recommend(self, *, user, package_name: str) -> LimitRecommendation | None:
        from apps.devices.models import ActivityLog
        from django.utils import timezone

        window_start = timezone.now().date() - timedelta(days=TRAILING_WINDOW_DAYS)
        logs = ActivityLog.objects.filter(
            user=user,
            target_type=ActivityLog.TargetType.APP,
            target_identifier=package_name,
            occurred_date__gte=window_start,
        )

        daily_totals = {}
        for log in logs:
            daily_totals[log.occurred_date] = daily_totals.get(log.occurred_date, 0) + log.minutes_used

        if not daily_totals:
            return None  # not enough data — caller should fall back to a sane default (e.g. 45m)

        values = list(daily_totals.values())
        base = median(values)

        active_goal_codes = set(
            user.goals.filter(is_active=True).values_list("goal", flat=True)
        )
        nudge_applies = bool(active_goal_codes & GOAL_RELATED_TO_REDUCTION)

        recommended = base * (1 - GOAL_NUDGE_FRACTION) if nudge_applies else base
        recommended = max(10, round(recommended / 5) * 5)  # round to nearest 5 minutes, floor 10

        rationale = f"Based on your median usage over the last {len(daily_totals)} tracked days"
        if nudge_applies:
            rationale += ", nudged down slightly to support your active goals"

        return LimitRecommendation(
            package_name=package_name,
            recommended_daily_minutes=int(recommended),
            based_on_days=len(daily_totals),
            rationale=rationale,
        )
