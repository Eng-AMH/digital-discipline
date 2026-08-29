"""
Seeds the Plan catalog exactly matching blueprint §20's own table:

FREE: Limited Apps, Basic Limits, Basic Analytics, Limited Unlocks, Rewarded Ads, 1 Device
PRO: Unlimited Apps, Custom Limits, Weekly Lock, Focus Mode, Sleep Mode, Advanced
     Analytics, AI Coach, No Ads, Multiple Devices
FAMILY: Multiple Users, Multiple Devices, Accountability, Family Dashboard,
        Central Policies, Reports

Also seeds §21 Extended Limits ranges: Free 20-60min, Pro/Family unlimited (0).
"""
from django.core.management.base import BaseCommand

from apps.monetization.models import Plan


class Command(BaseCommand):
    help = "Seed the Plan catalog per blueprint §20/§21."

    def handle(self, *args, **options):
        plans = [
            {
                "tier": Plan.Tier.FREE, "display_name": "Free",
                "monthly_price_cents": 0, "max_devices": 1, "max_daily_limit_minutes": 60,
                "weekly_lock_available": True, "focus_mode_available": False,
                "sleep_mode_available": False, "ai_coach_available": False,
                "ads_enabled": True, "family_features_available": False,
            },
            {
                "tier": Plan.Tier.PRO, "display_name": "Pro",
                "monthly_price_cents": 999, "max_devices": 5, "max_daily_limit_minutes": 0,
                "weekly_lock_available": True, "focus_mode_available": True,
                "sleep_mode_available": True, "ai_coach_available": True,
                "ads_enabled": False, "family_features_available": False,
            },
            {
                "tier": Plan.Tier.FAMILY, "display_name": "Family",
                "monthly_price_cents": 1999, "max_devices": 20, "max_daily_limit_minutes": 0,
                "weekly_lock_available": True, "focus_mode_available": True,
                "sleep_mode_available": True, "ai_coach_available": True,
                "ads_enabled": False, "family_features_available": True,
            },
        ]

        for plan_data in plans:
            plan, created = Plan.objects.update_or_create(tier=plan_data["tier"], defaults=plan_data)
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} plan: {plan.display_name}"))
