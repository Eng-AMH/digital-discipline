"""
Celery app + beat schedule.

Every entry here corresponds to a real scheduled job the blueprint requires, not a
placeholder. See architecture doc §0.3 point 5.
"""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("digital_discipline")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    # §17 Streaks + §19 Focus Score: nightly, just after midnight UTC. Deliberately
    # a single combined task (compute_focus_scores_and_streaks) rather than two
    # separate tasks, since streak update DEPENDS on that day's just-computed score
    # (architecture doc §8 — "a day counts toward streak if score >= STREAK_MIN_SCORE").
    "compute-daily-focus-scores": {
        "task": "apps.gamification.tasks.compute_focus_scores_and_streaks",
        "schedule": crontab(hour=0, minute=15),
    },
    # §5 Weekly Locked Plan: check for plans whose locked_until has passed, so the
    # dashboard's "Next modification" state is accurate without a request-time check
    # on every read (the model's is_currently_locked() is still the authoritative
    # check for enforcement — this task is for cleanup/notification only).
    "check-weekly-plan-unlocks": {
        "task": "apps.policies.tasks.notify_weekly_plan_unlocks",
        "schedule": crontab(minute="*/30"),
    },
    # §17 AI Coach weekly report — generated once a week, Monday morning, covering
    # the just-completed week.
    "generate-weekly-ai-reports": {
        "task": "apps.ai_coach.tasks.generate_weekly_reports_for_eligible_users",
        "schedule": crontab(hour=6, minute=0, day_of_week=1),
    },
    # §43 Achievements — rule evaluation. Runs after the nightly score computation
    # so achievements that depend on that day's score/streak (e.g. "30 Day Streak")
    # see up-to-date data.
    "evaluate-achievements": {
        "task": "apps.gamification.tasks.evaluate_achievements",
        "schedule": crontab(hour=1, minute=0),
    },
    # §35 Referral anti-abuse: qualification check runs independently of signup
    # time, confirming real usage before any reward is granted (architecture §10).
    "check-referral-qualifications": {
        "task": "apps.monetization.tasks.check_referral_qualifications",
        "schedule": crontab(hour="*/6", minute=0),
    },
    # §23 Subscription lifecycle: grace-period → expired transitions for
    # subscriptions whose current_period_end has passed with no renewal signal.
    "expire-lapsed-subscriptions": {
        "task": "apps.monetization.tasks.expire_lapsed_subscriptions",
        "schedule": crontab(hour="*/1", minute=0),
    },
    # §11 Unlock tokens: purge/mark-expired tokens past their expires_at that were
    # never redeemed, for admin visibility (not a correctness requirement — expired
    # tokens already fail redemption — but keeps the audit dashboard meaningful).
    "sweep-expired-unlock-tokens": {
        "task": "apps.policies.tasks.sweep_expired_unlock_tokens",
        "schedule": crontab(hour=2, minute=0),
    },
    # §9 Device Health: flag devices with no heartbeat in >30 minutes as
    # potentially tampered/offline, feeding the "⚠ Protection Interrupted" signal
    # even if the device itself never got to report the state change.
    "check-stale-device-heartbeats": {
        "task": "apps.devices.tasks.check_stale_heartbeats",
        "schedule": crontab(minute="*/15"),
    },
}
