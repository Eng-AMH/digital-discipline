from django.urls import path

from apps.policies import views

urlpatterns = [
    path("app-limits/", views.AppLimitListCreateView.as_view(), name="app-limit-list-create"),
    path("app-limits/<uuid:pk>/", views.AppLimitDetailView.as_view(), name="app-limit-detail"),

    path("website-limits/", views.WebsiteLimitListCreateView.as_view(), name="website-limit-list-create"),
    path("website-limits/<uuid:pk>/", views.WebsiteLimitDetailView.as_view(), name="website-limit-detail"),

    path("weekly-plans/", views.WeeklyPlanListCreateView.as_view(), name="weekly-plan-list-create"),
    path("weekly-plans/<uuid:plan_id>/confirm/", views.WeeklyPlanConfirmView.as_view(), name="weekly-plan-confirm"),

    path("schedules/", views.ScheduleListCreateView.as_view(), name="schedule-list-create"),
    path("schedules/<uuid:pk>/", views.ScheduleDetailView.as_view(), name="schedule-detail"),

    path("focus/start/", views.FocusSessionStartView.as_view(), name="focus-start"),
    path("focus/<uuid:session_id>/end/", views.FocusSessionEndView.as_view(), name="focus-end"),

    path("unlock/request/", views.UnlockRequestCreateView.as_view(), name="unlock-request-create"),
    path("unlock/<uuid:request_id>/decide/", views.UnlockRequestDecideView.as_view(), name="unlock-request-decide"),
    path("unlock/token/<uuid:token_id>/redeem/", views.UnlockTokenRedeemView.as_view(), name="unlock-token-redeem"),

    path("offline-blob/<uuid:device_id>/", views.OfflinePolicyBlobView.as_view(), name="offline-policy-blob"),
]
