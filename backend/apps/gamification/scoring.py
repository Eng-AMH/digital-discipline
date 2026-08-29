"""
Focus Score formula — the single source of truth for §19's scoring logic.

The blueprint (§16/§19) lists the INPUTS to the score (limit adherence, focus
sessions, consistency, night usage, weekly plan respect) but does not define a
formula. Leaving that undefined would make "87/100" an arbitrary, unexplainable
number. This module makes the formula explicit, tunable via named constants (not
inlined magic numbers), and documented — see architecture doc §8 for the weights.
"""
from dataclasses import dataclass
from datetime import date, timedelta

# Component weights — must sum to 100. Changing these changes the product's
# incentive structure, so they live here, named, not scattered as literals.
WEIGHT_LIMIT_ADHERENCE = 40
WEIGHT_FOCUS_COMPLETION = 25
WEIGHT_CONSISTENCY = 15
WEIGHT_NIGHT_USAGE = 10
WEIGHT_WEEKLY_PLAN = 10
assert (
    WEIGHT_LIMIT_ADHERENCE
    + WEIGHT_FOCUS_COMPLETION
    + WEIGHT_CONSISTENCY
    + WEIGHT_NIGHT_USAGE
    + WEIGHT_WEEKLY_PLAN
    == 100
)

# A day "counts" toward a Streak if that day's score meets this bar. Kept as a
# named constant (not e.g. hardcoded "70" in the Celery task) since it is a real
# product/business decision, not an implementation detail.
STREAK_MIN_SCORE = 60

# "Late night" window for the night-usage-penalty component.
NIGHT_WINDOW_START_HOUR = 22
NIGHT_WINDOW_END_HOUR = 5

WINDOW_DAYS = 7


@dataclass
class ScoreInputs:
    """Pre-aggregated inputs for one user, one 7-day window ending on `date`.
    Deliberately a plain dataclass (not an ORM query inline in compute_score) so
    the formula is unit-testable without a database."""
    limits_total: int
    limits_respected: int
    focus_sessions_started: int
    focus_sessions_completed: int
    active_days: int
    night_minutes: int
    total_minutes: int
    weekly_plan_breached: bool


@dataclass
class ScoreResult:
    total: int
    limit_adherence_component: float
    focus_completion_component: float
    consistency_component: float
    night_usage_component: float
    weekly_plan_component: float


def compute_score(inputs: ScoreInputs) -> ScoreResult:
    # Ground truth check first: has this user generated ANY tracked activity in
    # the window at all? This matters because several components below use a
    # "neutral, don't punish" default of 1.0 when their own denominator is zero
    # (e.g. no limits set yet, no focus sessions attempted) — which is correct
    # in isolation (an established user simply hasn't touched that feature this
    # week) but WRONG in combination for a user with zero activity overall, since
    # stacking multiple neutral defaults would silently produce a high score for
    # someone who hasn't used the product at all. `has_any_activity` gates this:
    # with no activity, only the fixed/structural components (consistency=0,
    # weekly_plan=neutral-if-no-plan) contribute, and the per-feature components
    # are NOT granted their neutral default.
    has_any_activity = inputs.total_minutes > 0 or inputs.active_days > 0

    # 1. Limit adherence rate
    if inputs.limits_total > 0:
        adherence_rate = inputs.limits_respected / inputs.limits_total
    elif not has_any_activity:
        adherence_rate = 0.0  # no activity at all — nothing to be neutral about
    else:
        adherence_rate = 1.0  # active user just hasn't set limits yet — don't penalize
    limit_component = WEIGHT_LIMIT_ADHERENCE * adherence_rate

    # 2. Focus session completion rate
    if inputs.focus_sessions_started > 0:
        completion_rate = inputs.focus_sessions_completed / inputs.focus_sessions_started
    elif not has_any_activity:
        completion_rate = 0.0
    else:
        completion_rate = 1.0  # active user just hasn't tried a focus session yet
    focus_component = WEIGHT_FOCUS_COMPLETION * completion_rate

    # 3. Consistency: fraction of the window the user was active at all. This is
    # the component that actually reflects "zero activity" honestly — it's 0 for
    # a user with no active_days, by construction, with no special-casing needed.
    consistency_rate = min(inputs.active_days / WINDOW_DAYS, 1.0)
    consistency_component = WEIGHT_CONSISTENCY * consistency_rate

    # 4. Night usage penalty (inverse — MORE night usage = LOWER component).
    # Zero total_minutes means zero night-usage risk, so full credit here is
    # correct even for a brand-new user — this component is fine as neutral.
    if inputs.total_minutes > 0:
        night_fraction = inputs.night_minutes / inputs.total_minutes
    else:
        night_fraction = 0.0
    night_component = WEIGHT_NIGHT_USAGE * max(0.0, 1.0 - night_fraction)

    # 5. Weekly plan respect — full credit if never breached during an active
    # locked plan, OR if there is no active locked plan at all (can't respect or
    # breach a plan that doesn't exist — this is a feature the user opts into,
    # like limits/focus sessions above, so the same "haven't used it yet" logic
    # applies and is NOT gated by has_any_activity: a user with genuinely zero
    # activity also, by definition, has no active locked plan to have breached).
    if inputs.weekly_plan_breached:
        weekly_component = 0.0
    else:
        weekly_component = WEIGHT_WEEKLY_PLAN

    total = round(
        limit_component + focus_component + consistency_component + night_component + weekly_component
    )
    total = max(0, min(100, total))

    return ScoreResult(
        total=total,
        limit_adherence_component=round(limit_component, 2),
        focus_completion_component=round(focus_component, 2),
        consistency_component=round(consistency_component, 2),
        night_usage_component=round(night_component, 2),
        weekly_plan_component=round(weekly_component, 2),
    )


def gather_score_inputs(*, user, for_date: date) -> ScoreInputs:
    """
    Real aggregation query against ActivityLog/AppLimit/FocusSession/WeeklyPlan for
    the 7-day window ending on `for_date`. Separated from compute_score() above so
    the pure formula stays unit-testable without touching the ORM.
    """
    from apps.devices.models import ActivityLog
    from apps.policies.models import AppLimit, FocusSession, WeeklyPlan

    window_start = for_date - timedelta(days=WINDOW_DAYS - 1)

    logs = ActivityLog.objects.filter(user=user, occurred_date__gte=window_start, occurred_date__lte=for_date)

    total_minutes = sum(l.minutes_used for l in logs)
    night_minutes = sum(
        l.minutes_used
        for l in logs
        if l.session_started_at.hour >= NIGHT_WINDOW_START_HOUR or l.session_started_at.hour < NIGHT_WINDOW_END_HOUR
    )
    active_days = len({l.occurred_date for l in logs})

    limits = list(AppLimit.objects.filter(user=user, is_enabled=True))
    limits_total = 0
    limits_respected = 0
    for limit in limits:
        used = sum(
            l.minutes_used
            for l in logs
            if l.target_type == ActivityLog.TargetType.APP and l.target_identifier == limit.package_name
        )
        # Each (limit, day-in-window) that had any usage counts as one adherence check.
        days_with_usage = {
            l.occurred_date
            for l in logs
            if l.target_type == ActivityLog.TargetType.APP and l.target_identifier == limit.package_name
        }
        for day in days_with_usage:
            day_used = sum(
                l.minutes_used
                for l in logs
                if l.occurred_date == day
                and l.target_type == ActivityLog.TargetType.APP
                and l.target_identifier == limit.package_name
            )
            limits_total += 1
            if day_used <= limit.daily_minutes:
                limits_respected += 1

    sessions = FocusSession.objects.filter(user=user, started_at__date__gte=window_start, started_at__date__lte=for_date)
    focus_started = sessions.count()
    focus_completed = sessions.filter(status=FocusSession.Status.COMPLETED).count()

    active_locked_plan = (
        WeeklyPlan.objects.filter(user=user, is_confirmed=True, locked_until__gte=for_date).first()
    )
    weekly_plan_breached = False
    if active_locked_plan:
        # A breach = any AppLimit under this plan exceeded on any day in the window.
        for limit in active_locked_plan.app_limits.all():
            for day in {l.occurred_date for l in logs if l.target_identifier == limit.package_name}:
                day_used = sum(
                    l.minutes_used for l in logs if l.occurred_date == day and l.target_identifier == limit.package_name
                )
                if day_used > limit.daily_minutes:
                    weekly_plan_breached = True
                    break

    return ScoreInputs(
        limits_total=limits_total,
        limits_respected=limits_respected,
        focus_sessions_started=focus_started,
        focus_sessions_completed=focus_completed,
        active_days=active_days,
        night_minutes=night_minutes,
        total_minutes=total_minutes,
        weekly_plan_breached=weekly_plan_breached,
    )
