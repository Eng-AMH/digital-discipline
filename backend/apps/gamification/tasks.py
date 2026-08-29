"""
Gamification Celery tasks — real scheduled jobs, not placeholders. Registered in
config/celery.py beat_schedule.
"""
from celery import shared_task
from django.db import models
from django.utils import timezone

from apps.core.models import write_audit_log, AuditLog


@shared_task
def compute_focus_scores_and_streaks():
    """
    §19 Focus Score + §17 Streaks, combined into one nightly task deliberately
    (see config/celery.py comment): streak update reads the score just computed
    for today, so they must run in the same task/transaction rather than as two
    independently-scheduled jobs that could race or run out of order.
    """
    from apps.accounts.models import User
    from apps.gamification.models import FocusScoreSnapshot, Streak
    from apps.gamification.scoring import gather_score_inputs, compute_score, STREAK_MIN_SCORE

    today = timezone.now().date()
    processed = 0

    for user in User.objects.filter(is_active=True, is_guest=False).iterator():
        inputs = gather_score_inputs(user=user, for_date=today)
        result = compute_score(inputs)

        FocusScoreSnapshot.objects.update_or_create(
            user=user,
            date=today,
            defaults={
                "score": result.total,
                "limit_adherence_component": result.limit_adherence_component,
                "focus_completion_component": result.focus_completion_component,
                "consistency_component": result.consistency_component,
                "night_usage_component": result.night_usage_component,
                "weekly_plan_component": result.weekly_plan_component,
            },
        )

        streak, _ = Streak.objects.get_or_create(user=user)
        yesterday = today - timezone.timedelta(days=1)

        if result.total >= STREAK_MIN_SCORE:
            if streak.last_counted_date == yesterday or streak.last_counted_date is None:
                streak.current_streak_days += 1
            elif streak.last_counted_date != today:
                # Gap in counted days — streak broken, restart at 1 for today.
                streak.current_streak_days = 1
            streak.last_counted_date = today
            streak.best_streak_days = max(streak.best_streak_days, streak.current_streak_days)
            streak.save()
        elif streak.last_counted_date != yesterday and streak.current_streak_days > 0:
            # Score fell below bar and there's no grace — streak resets to 0.
            # (last_counted_date is intentionally left as-is so we don't overwrite
            # history; current_streak_days is the only field reset here.)
            streak.current_streak_days = 0
            streak.save(update_fields=["current_streak_days"])

        processed += 1

    return {"processed_users": processed, "date": str(today)}


@shared_task
def evaluate_achievements():
    """
    §43 Achievements. Rule evaluation kept simple and explicit per-achievement-key
    rather than a generic rule engine — the blueprint's achievement list is fixed
    and small enough that explicit code is more auditable than a DSL would be.
    """
    from apps.accounts.models import User
    from apps.gamification.models import (
        Achievement, UserAchievement, Streak, TokenTransaction,
    )
    from apps.policies.models import FocusSession
    from apps.social.models import ChallengeMember, FriendRequest
    from apps.monetization.models import Referral

    unlocked_count = 0

    def unlock(user, key):
        nonlocal unlocked_count
        try:
            achievement = Achievement.objects.get(key=key)
        except Achievement.DoesNotExist:
            return  # achievement catalog not seeded yet — skip silently, not an error
        _, created = UserAchievement.objects.get_or_create(user=user, achievement=achievement)
        if created:
            unlocked_count += 1
            if achievement.token_reward > 0:
                TokenTransaction.objects.create(
                    user=user,
                    amount=achievement.token_reward,
                    reason=TokenTransaction.Reason.ACHIEVEMENT_UNLOCKED,
                    reference_id=str(achievement.id),
                )

    for user in User.objects.filter(is_active=True, is_guest=False).iterator():
        completed_sessions = FocusSession.objects.filter(user=user, status=FocusSession.Status.COMPLETED)
        if completed_sessions.exists():
            unlock(user, "first_focus_session")

        blocked_count = completed_sessions.count()  # proxy metric; refined once ActivityLog block-events exist
        if blocked_count >= 100:
            unlock(user, "100_successful_blocks")

        streak = Streak.objects.filter(user=user).first()
        if streak:
            if streak.best_streak_days >= 7:
                unlock(user, "7_day_streak")
            if streak.best_streak_days >= 30:
                unlock(user, "30_day_streak")

        if ChallengeMember.objects.filter(user=user).exists():
            unlock(user, "first_challenge")

        has_accepted_friend = FriendRequest.objects.filter(
            status=FriendRequest.Status.ACCEPTED
        ).filter(
            models.Q(from_user=user) | models.Q(to_user=user)
        ).exists()
        if has_accepted_friend:
            unlock(user, "first_friend")

        if Referral.objects.filter(referrer=user).exists():
            unlock(user, "first_referral")

    return {"unlocked": unlocked_count}
