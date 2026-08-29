from django.urls import path

from apps.monetization import views

urlpatterns = [
    path("plans/", views.PlanCatalogView.as_view(), name="plan-catalog"),
    path("subscription/", views.CurrentSubscriptionView.as_view(), name="current-subscription"),
    path("subscription/<uuid:subscription_id>/cancel/", views.SubscriptionCancelView.as_view(), name="subscription-cancel"),

    path("referral/code/", views.ReferralCodeView.as_view(), name="referral-code"),
    path("referral/signup/", views.ReferralSignupView.as_view(), name="referral-signup"),
    path("referral/mine/", views.ReferralListView.as_view(), name="referral-mine"),

    path("ambassador/signup/", views.AmbassadorSignupView.as_view(), name="ambassador-signup"),

    path("store/catalog/", views.StoreCatalogView.as_view(), name="store-catalog"),

    path("webhooks/stripe/", views.StripeWebhookView.as_view(), name="webhook-stripe"),
    path("webhooks/google-play/", views.GooglePlayWebhookView.as_view(), name="webhook-google-play"),
    path("webhooks/apple-iap/", views.AppleIAPWebhookView.as_view(), name="webhook-apple-iap"),
]
