from django.urls import path

from apps.accounts import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("me/", views.MeView.as_view(), name="me"),
    path("me/export/", views.AccountExportView.as_view(), name="account-export"),
    path("me/delete/", views.AccountDeleteView.as_view(), name="account-delete"),

    path("onboarding/", views.OnboardingStateView.as_view(), name="onboarding-state"),
    path("onboarding/advance/", views.advance_onboarding_step, name="onboarding-advance"),
    path("onboarding/explain-permissions/", views.explain_permissions, name="onboarding-explain-permissions"),
    path("onboarding/give-consent/", views.give_consent, name="onboarding-give-consent"),

    path("goals/", views.UserGoalListCreateView.as_view(), name="goals-list-create"),
    path("goals/<uuid:pk>/", views.UserGoalDeleteView.as_view(), name="goals-delete"),
]
