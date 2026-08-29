from django.urls import path

from apps.ai_coach import views

urlpatterns = [
    path("reports/", views.AICoachReportListView.as_view(), name="ai-coach-reports"),
    path("smart-limits/recommend/", views.SmartLimitRecommendationView.as_view(), name="smart-limit-recommend"),
    path("smart-limits/accept/", views.AcceptSmartLimitRecommendationView.as_view(), name="smart-limit-accept"),
]
