"""
EntitlementResolver — architecture doc §7.

Rather than scatter `if user.is_pro` checks through the codebase (which inevitably
drifts inconsistent), every feature that needs to know "is this allowed for this
user's plan" goes through resolve_entitlements(user) and reads the typed result.
This is also the extension point for §31/§32 (Schools/Companies via Organization)
later without touching call sites — an org-level override would slot in here.
"""
from dataclasses import dataclass

from django.utils import timezone


@dataclass(frozen=True)
class Entitlements:
    plan_tier: str
    max_devices: int
    max_daily_limit_minutes: int  # 0 = unlimited
    weekly_lock_available: bool
    focus_mode_available: bool
    sleep_mode_available: bool
    ai_coach_available: bool
    ads_enabled: bool
    family_features_available: bool

    def daily_limit_allowed(self, requested_minutes: int) -> bool:
        if self.max_daily_limit_minutes == 0:
            return True
        return requested_minutes <= self.max_daily_limit_minutes


def _free_plan_entitlements() -> Entitlements:
    """
    Fallback used when a user has no active Subscription row at all (e.g. brand
    new account before any Plan row is seeded, or subscription lapsed). Mirrors
    the FREE Plan's intended defaults from §20 so the resolver never crashes or
    silently grants Pro features when the Plan catalog table is empty/misconfigured
    — this is a deliberate fail-closed default, not fail-open.
    """
    return Entitlements(
        plan_tier="FREE",
        max_devices=1,
        max_daily_limit_minutes=60,
        weekly_lock_available=True,   # §20: Free tier DOES get weekly lock + basic limits —
        focus_mode_available=False,   # blueprint explicitly lists these as PRO-only additions
        sleep_mode_available=False,
        ai_coach_available=False,
        ads_enabled=True,
        family_features_available=False,
    )


def resolve_entitlements(user) -> Entitlements:
    from apps.monetization.models import Subscription

    active_sub = (
        Subscription.objects.filter(
            user=user,
            status__in=[Subscription.Status.ACTIVE, Subscription.Status.GRACE_PERIOD],
            current_period_end__gte=timezone.now(),
        )
        .select_related("plan")
        .order_by("-current_period_end")
        .first()
    )

    if active_sub is None:
        return _free_plan_entitlements()

    plan = active_sub.plan
    return Entitlements(
        plan_tier=plan.tier,
        max_devices=plan.max_devices,
        max_daily_limit_minutes=plan.max_daily_limit_minutes,
        weekly_lock_available=plan.weekly_lock_available,
        focus_mode_available=plan.focus_mode_available,
        sleep_mode_available=plan.sleep_mode_available,
        ai_coach_available=plan.ai_coach_available,
        ads_enabled=plan.ads_enabled,
        family_features_available=plan.family_features_available,
    )
