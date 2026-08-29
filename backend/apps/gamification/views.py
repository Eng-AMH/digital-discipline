"""
Gamification views. §18 Focus Tokens balance is ALWAYS computed via
SUM(TokenTransaction.amount) — see TokenBalanceView — never read from a stored
field, per architecture doc §4's ledger design decision.
"""
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.gamification.models import FocusScoreSnapshot, Streak, TokenTransaction, Achievement, UserAchievement
from apps.gamification.serializers import (
    FocusScoreSnapshotSerializer, StreakSerializer, TokenTransactionSerializer,
    AchievementSerializer, UserAchievementSerializer,
)


class FocusScoreHistoryView(generics.ListAPIView):
    """§16/§19: powers dashboard trend charts."""
    serializer_class = FocusScoreSnapshotSerializer

    def get_queryset(self):
        return FocusScoreSnapshot.objects.filter(user=self.request.user).order_by("-date")[:90]


class StreakView(generics.RetrieveAPIView):
    """§17 Streaks."""
    serializer_class = StreakSerializer

    def get_object(self):
        streak, _ = Streak.objects.get_or_create(user=self.request.user)
        return streak


class TokenBalanceView(APIView):
    """§18: balance = SUM(ledger), computed on read, never stored — see module
    docstring and architecture doc §4."""

    def get(self, request):
        balance = TokenTransaction.objects.filter(user=request.user).aggregate(total=Sum("amount"))["total"] or 0
        return Response({"balance": balance})


class TokenTransactionHistoryView(generics.ListAPIView):
    serializer_class = TokenTransactionSerializer

    def get_queryset(self):
        return TokenTransaction.objects.filter(user=self.request.user)


class AchievementCatalogView(generics.ListAPIView):
    """§43: full catalog, so the UI can show locked/unlocked state."""
    serializer_class = AchievementSerializer
    queryset = Achievement.objects.all()


class UserAchievementListView(generics.ListAPIView):
    serializer_class = UserAchievementSerializer

    def get_queryset(self):
        return UserAchievement.objects.filter(user=self.request.user).select_related("achievement")


class StorePurchaseView(APIView):
    """
    §30 Cosmetic Store, token-purchase path. Real-money purchase path is
    architected (StoreItem.real_money_price_cents) but not wired to a payment
    provider in this phase, per architecture doc §0.2 — this view handles the
    token-purchase path only, which needs no external provider.
    """

    @transaction.atomic
    def post(self, request):
        from apps.monetization.models import StoreItem, UserInventory
        from apps.monetization.entitlements import resolve_entitlements

        item = get_object_or_404(StoreItem, id=request.data.get("item_id"))
        if item.token_price is None:
            return Response({"detail": "This item is not purchasable with tokens."}, status=status.HTTP_400_BAD_REQUEST)

        if item.requires_plan_tier:
            entitlements = resolve_entitlements(request.user)
            if entitlements.plan_tier != item.requires_plan_tier:
                return Response(
                    {"detail": f"This item requires the {item.requires_plan_tier} plan."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        already_owned = UserInventory.objects.filter(user=request.user, item=item).exists()
        if already_owned:
            return Response({"detail": "You already own this item."}, status=status.HTTP_400_BAD_REQUEST)

        # Correctness note: an atomic block alone does NOT prevent two concurrent
        # requests from both reading the same balance before either writes its
        # debit — that would allow a double-spend under real concurrent load.
        # select_for_update() here locks this user's existing TokenTransaction
        # rows for the duration of the transaction, so a second concurrent
        # purchase request blocks until the first commits and sees the debited
        # balance. This is the actual protection, not just @transaction.atomic.
        locked_qs = TokenTransaction.objects.select_for_update().filter(user=request.user)
        balance = locked_qs.aggregate(total=Sum("amount"))["total"] or 0
        if balance < item.token_price:
            return Response({"detail": "Insufficient token balance."}, status=status.HTTP_402_PAYMENT_REQUIRED)

        TokenTransaction.objects.create(
            user=request.user, amount=-item.token_price,
            reason=TokenTransaction.Reason.SPENT_STORE_PURCHASE, reference_id=str(item.id),
        )
        UserInventory.objects.create(user=request.user, item=item)

        return Response({"detail": "Purchase successful.", "item_id": str(item.id)}, status=status.HTTP_201_CREATED)
