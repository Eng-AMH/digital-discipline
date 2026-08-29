"""
Seeds the Achievement catalog matching blueprint §43's exact list:
First Focus Session, 7 Day Streak, 30 Day Streak, 100 Successful Blocks,
10 Hours Saved, First Challenge, First Friend, First Referral.
"""
from django.core.management.base import BaseCommand

from apps.gamification.models import Achievement


class Command(BaseCommand):
    help = "Seed the Achievement catalog per blueprint §43."

    def handle(self, *args, **options):
        achievements = [
            {"key": "first_focus_session", "title": "First Focus Session", "description": "Completed your first Focus Session.", "icon": "🎯", "token_reward": 10},
            {"key": "7_day_streak", "title": "7 Day Streak", "description": "Maintained a 7-day Focus Score streak.", "icon": "🔥", "token_reward": 20},
            {"key": "30_day_streak", "title": "30 Day Streak", "description": "Maintained a 30-day Focus Score streak.", "icon": "🔥", "token_reward": 100},
            {"key": "100_successful_blocks", "title": "100 Successful Blocks", "description": "Your limits successfully blocked 100 attempts.", "icon": "🛡️", "token_reward": 30},
            {"key": "10_hours_saved", "title": "10 Hours Saved", "description": "Saved 10 hours of screen time versus your limits.", "icon": "⏱️", "token_reward": 25},
            {"key": "first_challenge", "title": "First Challenge", "description": "Joined your first Challenge.", "icon": "🏆", "token_reward": 15},
            {"key": "first_friend", "title": "First Friend", "description": "Made your first friend connection.", "icon": "🤝", "token_reward": 10},
            {"key": "first_referral", "title": "First Referral", "description": "Referred your first friend to the platform.", "icon": "💌", "token_reward": 15},
        ]

        for data in achievements:
            achievement, created = Achievement.objects.update_or_create(key=data["key"], defaults=data)
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} achievement: {achievement.title}"))
