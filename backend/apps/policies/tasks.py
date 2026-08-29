"""
Policy-related Celery tasks. See config/celery.py beat_schedule for cadence.
"""
from celery import shared_task
from django.utils import timezone


@shared_task
def notify_weekly_plan_unlocks():
    """
    §5 Weekly Locked Plan. Finds plans whose lock JUST expired (within the last
    30-minute window, matching this task's schedule) and fires a notification so
    the user knows they can now adjust their plan — the model's own
    is_currently_locked() remains the authoritative enforcement check; this task
    exists purely for the notification side-effect, not correctness.
    """
    from apps.policies.models import WeeklyPlan
    from apps.notifications.models import Notification, NotificationType

    now = timezone.now()
    window_start = now - timezone.timedelta(minutes=30)

    newly_unlocked = WeeklyPlan.objects.filter(
        is_confirmed=True, locked_until__gte=window_start, locked_until__lte=now
    )

    notified = 0
    for plan in newly_unlocked:
        Notification.objects.create(
            user=plan.user,
            notification_type=NotificationType.WEEKLY_PLAN_UNLOCKED,
            title="Your weekly plan is unlocked",
            body="You can now adjust your app limits until you confirm your next weekly plan.",
            metadata={"weekly_plan_id": str(plan.id)},
        )
        notified += 1

    return {"notified": notified}


@shared_task
def sweep_expired_unlock_tokens():
    """
    §11 Unlock tokens. Purely for admin/audit dashboard cleanliness (architecture
    doc §0.3) — expired tokens already fail redemption via the expires_at check in
    apps.policies.services.redeem_unlock_token, so this task has no correctness
    impact, only visibility impact.
    """
    from apps.policies.models import UnlockToken

    now = timezone.now()
    expired_unredeemed = UnlockToken.objects.filter(redeemed_at__isnull=True, expires_at__lt=now)
    count = expired_unredeemed.count()
    # Not deleted — kept for audit trail (matches AuditLog's own append-only
    # philosophy); this task's real job is just counting/reporting for now.
    return {"expired_unredeemed_count": count}
