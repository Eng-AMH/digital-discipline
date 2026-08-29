from django.core.management.base import BaseCommand


TASKS = [
    ("daily focus scores", "apps.gamification.tasks.compute_focus_scores_and_streaks"),
    ("weekly plan unlock notices", "apps.policies.tasks.notify_weekly_plan_unlocks"),
    ("weekly AI reports", "apps.ai_coach.tasks.generate_weekly_reports_for_eligible_users"),
    ("achievements", "apps.gamification.tasks.evaluate_achievements"),
    ("referral qualification", "apps.monetization.tasks.check_referral_qualifications"),
    ("expired subscriptions", "apps.monetization.tasks.expire_lapsed_subscriptions"),
    ("expired unlock token sweep", "apps.policies.tasks.sweep_expired_unlock_tokens"),
    ("stale device heartbeats", "apps.devices.tasks.check_stale_heartbeats"),
]


class Command(BaseCommand):
    help = "Run scheduled maintenance tasks synchronously (free-tier friendly)."

    def handle(self, *args, **options):
        for label, dotted_path in TASKS:
            module_name, func_name = dotted_path.rsplit(".", 1)
            module = __import__(module_name, fromlist=[func_name])
            task = getattr(module, func_name)
            self.stdout.write(f"Running {label}...")
            result = task()
            self.stdout.write(self.style.SUCCESS(f"  {result}"))
        self.stdout.write(self.style.SUCCESS("Scheduled tasks completed."))
