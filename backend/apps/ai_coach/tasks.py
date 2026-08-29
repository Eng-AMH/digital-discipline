"""
AI Coach Celery tasks. See config/celery.py beat_schedule for cadence
(Monday mornings, covering the just-completed week).
"""
from celery import shared_task
from django.utils import timezone


@shared_task
def generate_weekly_reports_for_eligible_users():
    """
    §17 AI Coach weekly report. "Eligible" = entitlements.ai_coach_available is
    True (Pro/Family plans per §20) AND the user has at least some ActivityLog
    data in the completed week — generating a report from zero data would be
    either empty or fabricated, neither of which is acceptable.
    """
    from apps.accounts.models import User
    from apps.devices.models import ActivityLog
    from apps.ai_coach.models import AICoachReport
    from apps.ai_coach.services import get_ai_coach_provider, WeeklyReportInputs
    from apps.monetization.entitlements import resolve_entitlements

    today = timezone.now().date()
    period_end = today - timezone.timedelta(days=today.weekday() + 1)  # last Sunday
    period_start = period_end - timezone.timedelta(days=6)
    prior_period_start = period_start - timezone.timedelta(days=7)
    prior_period_end = period_start - timezone.timedelta(days=1)

    provider = get_ai_coach_provider()
    generated = 0

    for user in User.objects.filter(is_active=True, is_guest=False).iterator():
        entitlements = resolve_entitlements(user)
        if not entitlements.ai_coach_available:
            continue

        week_logs = ActivityLog.objects.filter(user=user, occurred_date__gte=period_start, occurred_date__lte=period_end)
        if not week_logs.exists():
            continue

        prior_logs = ActivityLog.objects.filter(
            user=user, occurred_date__gte=prior_period_start, occurred_date__lte=prior_period_end
        )

        total_minutes = sum(l.minutes_used for l in week_logs)
        prior_total_minutes = sum(l.minutes_used for l in prior_logs)

        social_media_packages = {
            "com.instagram.android", "com.zhiliaoapp.musically", "com.facebook.katana",
            "com.twitter.android", "com.snapchat.android",
        }
        social_minutes = sum(
            l.minutes_used for l in week_logs
            if l.target_type == ActivityLog.TargetType.APP and l.target_identifier in social_media_packages
        )

        by_app = {}
        by_hour = {}
        for log in week_logs:
            by_app[log.target_identifier] = by_app.get(log.target_identifier, 0) + log.minutes_used
            hour = log.session_started_at.hour
            by_hour[hour] = by_hour.get(hour, 0) + log.minutes_used

        most_used_app = max(by_app, key=by_app.get) if by_app else "N/A"
        peak_hour = max(by_hour, key=by_hour.get) if by_hour else 21
        usage_window = f"{peak_hour % 12 or 12} {'AM' if peak_hour < 12 else 'PM'} – {(peak_hour + 2) % 12 or 12} {'AM' if (peak_hour + 2) % 24 < 12 else 'PM'}"

        # "Most problematic" = highest usage among apps that ALSO have an AppLimit
        # set (i.e. the user is actively trying to restrict it) — more meaningful
        # than raw usage rank, which would just always be a messaging app.
        from apps.policies.models import AppLimit
        limited_packages = set(AppLimit.objects.filter(user=user, is_enabled=True).values_list("package_name", flat=True))
        problematic_candidates = {k: v for k, v in by_app.items() if k in limited_packages}
        most_problematic = max(problematic_candidates, key=problematic_candidates.get) if problematic_candidates else most_used_app

        active_goals = list(user.goals.filter(is_active=True).values_list("goal", flat=True))

        # blocked_attempts / limits_respected_percent / time_saved are approximated
        # from AppLimit adherence here; a dedicated BlockEvent model would make this
        # exact — noted as a refinement opportunity in the requirements audit rather
        # than silently presented as more precise than it is.
        limits = AppLimit.objects.filter(user=user, is_enabled=True)
        respected_days = 0
        total_checks = 0
        blocked_attempts_estimate = 0
        for limit in limits:
            days_used = {l.occurred_date for l in week_logs if l.target_identifier == limit.package_name}
            for day in days_used:
                day_total = sum(l.minutes_used for l in week_logs if l.occurred_date == day and l.target_identifier == limit.package_name)
                total_checks += 1
                if day_total <= limit.daily_minutes:
                    respected_days += 1
                else:
                    blocked_attempts_estimate += 1

        limits_respected_percent = (respected_days / total_checks * 100) if total_checks else 100.0
        time_saved_estimate = sum(max(0, limit.daily_minutes * 7 - by_app.get(limit.package_name, 0)) for limit in limits)

        from apps.policies.models import FocusSession
        focus_completed = FocusSession.objects.filter(
            user=user, started_at__date__gte=period_start, started_at__date__lte=period_end,
            status=FocusSession.Status.COMPLETED,
        ).count()

        inputs = WeeklyReportInputs(
            user_display_name=user.display_name or user.email,
            total_screen_time_minutes=total_minutes,
            prior_week_screen_time_minutes=prior_total_minutes,
            social_media_minutes=social_minutes,
            biggest_usage_window=usage_window,
            most_used_app=most_used_app,
            most_problematic_app=most_problematic,
            blocked_attempts=blocked_attempts_estimate,
            limits_respected_percent=limits_respected_percent,
            time_saved_minutes=time_saved_estimate,
            focus_sessions_completed=focus_completed,
            active_goals=active_goals,
        )

        result = provider.generate_weekly_report(inputs)

        AICoachReport.objects.update_or_create(
            user=user,
            period=AICoachReport.Period.WEEKLY,
            period_start=period_start,
            defaults={
                "period_end": period_end,
                "biggest_usage_period": result["biggest_usage_period"],
                "screen_time_change_percent": result["screen_time_change_percent"],
                "most_problematic_app": result["most_problematic_app"],
                "narrative_text": result["narrative_text"],
                "recommendation_text": result["recommendation_text"],
                "generated_by": "mock" if provider.__class__.__name__ == "MockAICoachProvider" else provider.__class__.__name__,
            },
        )

        from apps.notifications.models import Notification, NotificationType
        Notification.objects.create(
            user=user,
            notification_type=NotificationType.WEEKLY_AI_REPORT_READY,
            title="Your weekly AI Coach report is ready",
            body=result["narrative_text"][:200],
        )

        generated += 1

    return {"generated": generated}
