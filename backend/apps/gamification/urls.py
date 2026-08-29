from django.urls import path

from apps.gamification import views

urlpatterns = [
    path("focus-score/history/", views.FocusScoreHistoryView.as_view(), name="focus-score-history"),
    path("streak/", views.StreakView.as_view(), name="streak"),
    path("tokens/balance/", views.TokenBalanceView.as_view(), name="token-balance"),
    path("tokens/history/", views.TokenTransactionHistoryView.as_view(), name="token-history"),
    path("achievements/catalog/", views.AchievementCatalogView.as_view(), name="achievement-catalog"),
    path("achievements/mine/", views.UserAchievementListView.as_view(), name="achievement-mine"),
    path("store/purchase/", views.StorePurchaseView.as_view(), name="store-purchase"),
]
