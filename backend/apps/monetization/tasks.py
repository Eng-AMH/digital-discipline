"""
Monetization Celery tasks. See config/celery.py beat_schedule for cadence.
"""
from celery import shared_task
from django.utils import timezone

REFERRAL_QUALIFICATION_MIN_ACTIVE_DAYS = 3

# §32 reward tiers, taken directly from the blueprint's own table.
REFERRAL_REWARD_TIERS = [
    (1, 7), (3, 30), (5, 60), (10, 180),
]  # (friends_referred, pro_days_granted) — cumulative thresholds


@shared_task
def check_referral_qualifications():
    """
    §35/§39 Referral anti-abuse. A referral only QUALIFIES (and only then grants a
    reward) once the referred user has real ActivityLog data across at least
    REFERRAL_QUALIFICATION_MIN_ACTIVE_DAYS distinct days — NOT at signup. This is
    the concrete mechanism that defeats "create 50 empty accounts," which the
    blueprint names explicitly in §39.
    """
    from apps.monetization.models import Referral, Subscription, Plan
    from apps.devices.models import ActivityLog
    from apps.core.models import write_audit_log, AuditLog

    pending = Referral.objects.filter(status=Referral.Status.SIGNED_UP)
    qualified_count = 0

    for referral in pending:
        active_days = (
            ActivityLog.objects.filter(user=referral.referred_user)
            .values_list("occurred_date", flat=True)
            .distinct()
            .count()
        )
        if active_days < REFERRAL_QUALIFICATION_MIN_ACTIVE_DAYS:
            continue

        referral.status = Referral.Status.QUALIFIED
        referral.qualified_at = timezone.now()

        prior_qualified_count = Referral.objects.filter(
            referrer=referral.referrer, status=Referral.Status.QUALIFIED
        ).count()
        this_referral_rank = prior_qualified_count + 1  # 1-indexed count including this one

        days_granted = 0
        for threshold, days in REFERRAL_REWARD_TIERS:
            if this_referral_rank >= threshold:
                days_granted = days
        referral.reward_granted_days = days_granted
        referral.save()

        if days_granted > 0:
            pro_plan = Plan.objects.filter(tier=Plan.Tier.PRO).first()
            if pro_plan:
                now = timezone.now()
                Subscription.objects.create(
                    user=referral.referrer,
                    plan=pro_plan,
                    status=Subscription.Status.ACTIVE,
                    source=Subscription.Source.PROMOTIONAL,
                    current_period_start=now,
                    current_period_end=now + timezone.timedelta(days=days_granted),
                )

        write_audit_log(
            AuditLog.EventType.SUBSCRIPTION_ACTIVATED if days_granted > 0 else AuditLog.EventType.POLICY_MODIFIED,
            actor=referral.referrer,
            target=referral,
            metadata={"days_granted": days_granted, "referral_rank": this_referral_rank},
        )
        qualified_count += 1

    return {"qualified": qualified_count}


@shared_task
def expire_lapsed_subscriptions():
    """§20/§47 Subscription lifecycle — ACTIVE/GRACE_PERIOD → EXPIRED once
    current_period_end has passed with no renewal (i.e. no new Subscription row
    with a later period was created by a webhook handler in the meantime)."""
    from apps.monetization.models import Subscription

    now = timezone.now()
    lapsed = Subscription.objects.filter(
        status__in=[Subscription.Status.ACTIVE, Subscription.Status.GRACE_PERIOD],
        current_period_end__lt=now,
    )
    count = lapsed.update(status=Subscription.Status.EXPIRED)
    return {"expired": count}
