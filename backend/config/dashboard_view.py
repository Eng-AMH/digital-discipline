"""
Dashboard aggregation — §12/§15 Main Dashboard. Deliberately lives outside any
single app (in config/, imported by config/urls.py) since it genuinely reads
across devices/policies/gamification — putting it inside one of those apps would
misleadingly suggest it "belongs" to that domain.

Returns exactly the shape the blueprint's own example lays out: Focus Score,
Screen Time, Social Media time, Time Saved, then a per-app table with
used/limit/status.
"""
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

SOCIAL_MEDIA_PACKAGES = {
    "com.instagram.android", "com.zhiliaoapp.musically", "com.facebook.katana",
    "com.twitter.android", "com.snapchat.android",
}


class DashboardView(APIView):
    def get(self, request):
        from apps.devices.models import ActivityLog
        from apps.policies.models import AppLimit
        from apps.gamification.models import FocusScoreSnapshot, TokenTransaction
        from django.db.models import Sum

        today = timezone.now().date()

        today_logs = ActivityLog.objects.filter(user=request.user, occurred_date=today)
        by_app = {}
        for log in today_logs:
            if log.target_type == ActivityLog.TargetType.APP:
                by_app[log.target_identifier] = by_app.get(log.target_identifier, 0) + log.minutes_used

        total_screen_time = sum(by_app.values())
        social_media_time = sum(v for k, v in by_app.items() if k in SOCIAL_MEDIA_PACKAGES)

        latest_score = FocusScoreSnapshot.objects.filter(user=request.user).order_by("-date").first()

        limits = AppLimit.objects.filter(user=request.user, is_enabled=True)
        app_rows = []
        time_saved_minutes = 0
        for limit in limits:
            used = by_app.get(limit.package_name, 0)
            if used >= limit.daily_minutes:
                app_status = "LOCKED"
            elif used >= limit.daily_minutes * 0.8:
                app_status = "WARNING"
            else:
                app_status = "OK"
            time_saved_minutes += max(0, limit.daily_minutes - used)
            app_rows.append({
                "package_name": limit.package_name,
                "display_name": limit.display_name,
                "used_minutes": used,
                "limit_minutes": limit.daily_minutes,
                "status": app_status,
            })

        return Response({
            "focus_score": latest_score.score if latest_score else None,
            "screen_time_minutes": total_screen_time,
            "social_media_minutes": social_media_time,
            "time_saved_minutes": time_saved_minutes,
            "apps": app_rows,
        })
