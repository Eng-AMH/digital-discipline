"""
Root URL configuration. See docs/01-REQUIREMENTS-AND-ARCHITECTURE.md §12 for the
full endpoint list this maps against.
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenBlacklistView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.dashboard_view import DashboardView


def health_check(request):
    return JsonResponse({"status": "ok"})

urlpatterns = [
    path("health/", health_check, name="health"),
    path("admin/", admin.site.urls),

    # §48 Security: JWT auth. Login = obtain pair, /auth/refresh/ rotates (see
    # SIMPLE_JWT ROTATE_REFRESH_TOKENS=True), /auth/logout/ blacklists.
    path("api/auth/login/", TokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("api/auth/logout/", TokenBlacklistView.as_view(), name="token-blacklist"),

    path("api/accounts/", include("apps.accounts.urls")),
    path("api/devices/", include("apps.devices.urls")),
    path("api/policies/", include("apps.policies.urls")),
    path("api/gamification/", include("apps.gamification.urls")),
    path("api/social/", include("apps.social.urls")),
    path("api/monetization/", include("apps.monetization.urls")),
    path("api/ai-coach/", include("apps.ai_coach.urls")),
    path("api/notifications/", include("apps.notifications.urls")),

    # §12/§15 Main Dashboard — cross-app aggregation, see config/dashboard_view.py
    path("api/dashboard/", DashboardView.as_view(), name="dashboard"),

    # API schema/docs (drf-spectacular) — useful for the eventual web/iOS clients
    # to consume this API without hand-written docs drifting from reality.
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="schema-docs"),
]
