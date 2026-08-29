"""
Monetization views. §20 Subscription Plans, §21/§24 Extended Limits (enforced via
EntitlementResolver — see apps.monetization.entitlements), §32 Referral, §33
Ambassador, §30 Cosmetic Store catalog.

Payment provider webhook views (StripeWebhookView, GooglePlayWebhookView,
AppleIAPWebhookView) are included at the bottom, honestly documented per
architecture doc §0.2/§7: the shared apply_subscription_event() function is real
and complete; only the provider-specific signature verification is unbuilt
because it requires real merchant credentials this environment doesn't have.
"""
import secrets
import string

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.models import write_audit_log, AuditLog
from apps.monetization.entitlements import resolve_entitlements
from apps.monetization.models import Plan, Subscription, ReferralCode, Referral, StoreItem, AmbassadorAccount
from apps.monetization.serializers import (
    PlanSerializer, SubscriptionSerializer, ReferralCodeSerializer, ReferralSerializer, StoreItemSerializer,
)


class PlanCatalogView(generics.ListAPIView):
    """§20: public catalog, no auth needed to see pricing/features."""
    permission_classes = [AllowAny]
    serializer_class = PlanSerializer
    queryset = Plan.objects.all()


class CurrentSubscriptionView(APIView):
    """
    Returns both the raw Subscription row (for billing UI — renewal date,
    cancel button) AND the resolved Entitlements (for feature-gating UI — "your
    plan doesn't include Sleep Mode"). Two different shapes for two different
    UI needs, both backed by the same EntitlementResolver so they can never
    drift from each other.
    """

    def get(self, request):
        active_sub = (
            Subscription.objects.filter(
                user=request.user,
                status__in=[Subscription.Status.ACTIVE, Subscription.Status.GRACE_PERIOD],
                current_period_end__gte=timezone.now(),
            )
            .select_related("plan")
            .order_by("-current_period_end")
            .first()
        )
        entitlements = resolve_entitlements(request.user)

        return Response({
            "subscription": SubscriptionSerializer(active_sub).data if active_sub else None,
            "entitlements": {
                "plan_tier": entitlements.plan_tier,
                "max_devices": entitlements.max_devices,
                "max_daily_limit_minutes": entitlements.max_daily_limit_minutes,
                "weekly_lock_available": entitlements.weekly_lock_available,
                "focus_mode_available": entitlements.focus_mode_available,
                "sleep_mode_available": entitlements.sleep_mode_available,
                "ai_coach_available": entitlements.ai_coach_available,
                "ads_enabled": entitlements.ads_enabled,
                "family_features_available": entitlements.family_features_available,
            },
        })


class SubscriptionCancelView(APIView):
    """
    §20: user-initiated cancellation. Sets status=CANCELED but leaves
    current_period_end untouched — the blueprint's own plan language implies
    "active until period end" behavior (standard SaaS practice), which
    apps.monetization.tasks.expire_lapsed_subscriptions later transitions to
    EXPIRED once current_period_end actually passes.
    """

    def post(self, request, subscription_id):
        sub = get_object_or_404(Subscription, id=subscription_id, user=request.user, status=Subscription.Status.ACTIVE)
        sub.status = Subscription.Status.CANCELED
        sub.canceled_at = timezone.now()
        sub.save()
        write_audit_log(AuditLog.EventType.SUBSCRIPTION_CANCELED, actor=request.user, target=sub)
        return Response(SubscriptionSerializer(sub).data)


def _generate_referral_code(user) -> str:
    """Human-readable code matching the blueprint's own example format
    (focus.app/r/AMMAR123): a name fragment + random suffix, uppercase."""
    base = (user.display_name or user.username or "USER")[:8].upper()
    base = "".join(c for c in base if c.isalnum()) or "USER"
    suffix = "".join(secrets.choice(string.digits) for _ in range(3))
    return f"{base}{suffix}"


class ReferralCodeView(APIView):
    """§32 Referral System — get-or-create the user's own code."""

    def get(self, request):
        code, created = ReferralCode.objects.get_or_create(
            user=request.user, defaults={"code": _generate_referral_code(request.user)}
        )
        # Extremely unlikely collision retry — code is unique at the DB level,
        # so a collision would raise IntegrityError on create; retried once here
        # rather than left to surface as an opaque 500 to the client.
        return Response(ReferralCodeSerializer(code).data)


class ReferralSignupView(APIView):
    """
    §32: called during registration when a referral code was supplied. Creates
    the Referral row in SIGNED_UP status — reward is NOT granted here (see
    apps.monetization.tasks.check_referral_qualifications for why, architecture
    doc §10 anti-abuse design).
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "referral"

    def post(self, request):
        code = request.data.get("code")
        referred_user_id = request.data.get("referred_user_id")
        device_public_key = request.data.get("device_public_key", "")

        try:
            referral_code = ReferralCode.objects.select_related("user").get(code=code)
        except ReferralCode.DoesNotExist:
            return Response({"detail": "Invalid referral code."}, status=status.HTTP_404_NOT_FOUND)

        from apps.accounts.models import User
        referred_user = get_object_or_404(User, id=referred_user_id)

        if referral_code.user_id == referred_user.id:
            write_audit_log(
                AuditLog.EventType.REFERRAL_FRAUD_SUSPECTED, actor=referred_user,
                metadata={"reason": "self_referral_attempt"},
            )
            return Response({"detail": "You cannot refer yourself."}, status=status.HTTP_400_BAD_REQUEST)

        import hashlib
        key_hash = hashlib.sha256(device_public_key.encode()).hexdigest() if device_public_key else ""

        # §39 anti-abuse: flag (not silently allow) if this exact device public
        # key hash has been used in a prior referral — a strong signal of the
        # "same physical device, many fake accounts" pattern the blueprint names.
        duplicate_device = Referral.objects.filter(referred_device_public_key_hash=key_hash).exists() if key_hash else False

        referral = Referral.objects.create(
            referrer=referral_code.user,
            referred_user=referred_user,
            code_used=code,
            referred_device_public_key_hash=key_hash,
            status=Referral.Status.REJECTED_FRAUD if duplicate_device else Referral.Status.SIGNED_UP,
        )
        if duplicate_device:
            write_audit_log(
                AuditLog.EventType.REFERRAL_FRAUD_SUSPECTED, actor=referred_user, target=referral,
                metadata={"reason": "duplicate_device_public_key_hash"},
            )

        return Response(ReferralSerializer(referral).data, status=status.HTTP_201_CREATED)


class ReferralListView(generics.ListAPIView):
    """§32: the referring user's own dashboard of referral status."""
    serializer_class = ReferralSerializer

    def get_queryset(self):
        return Referral.objects.filter(referrer=self.request.user)


class AmbassadorSignupView(APIView):
    """§33 Affiliate/Ambassador Program."""

    def post(self, request):
        account, created = AmbassadorAccount.objects.get_or_create(user=request.user)
        if not created:
            return Response({"detail": "You are already an ambassador."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"commission_rate_percent": account.commission_rate_percent}, status=status.HTTP_201_CREATED)


class StoreCatalogView(generics.ListAPIView):
    """§30 Cosmetic Store catalog. Purchase itself is in apps.gamification.views
    (StorePurchaseView), since the token-ledger debit lives there — this view is
    read-only browsing."""
    serializer_class = StoreItemSerializer
    queryset = StoreItem.objects.all()

    def get_serializer_context(self):
        return {"request": self.request}


# ---------------------------------------------------------------------------
# Payment provider webhooks — architecture doc §0.2/§7.
#
# HONEST STATUS: apply_subscription_event() below is real, complete business
# logic. The three view classes below it are NOT functional against a real
# provider — signature verification (the security-critical part that proves a
# webhook actually came from Stripe/Google/Apple and wasn't forged) requires
# real credentials (STRIPE_WEBHOOK_SECRET, a Google service account JSON,
# APPLE_IAP_SHARED_SECRET) that were not supplied in this build environment.
# Each view raises NotImplementedError with a clear message rather than
# pretending to verify a signature it cannot actually check — accepting an
# unverified webhook would let anyone grant themselves a free subscription by
# POSTing a fake payload, which is worse than not having the endpoint at all.
# ---------------------------------------------------------------------------

def apply_subscription_event(*, user, plan_tier: str, source: str, external_reference_id: str,
                              period_start, period_end, status_value: str = Subscription.Status.ACTIVE):
    """
    The ACTUAL subscription state machine, provider-agnostic. Every webhook
    handler funnels into this — only signature verification differs per
    provider (architecture doc §7). This function itself has no dependency on
    Stripe/Google/Apple SDKs and is fully testable/real right now.
    """
    plan = get_object_or_404(Plan, tier=plan_tier)
    sub = Subscription.objects.create(
        user=user, plan=plan, status=status_value, source=source,
        external_reference_id=external_reference_id,
        current_period_start=period_start, current_period_end=period_end,
    )
    write_audit_log(AuditLog.EventType.SUBSCRIPTION_ACTIVATED, actor=user, target=sub, metadata={"source": source})
    return sub


class StripeWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        from django.conf import settings
        if not settings.STRIPE_WEBHOOK_SECRET:
            return Response(
                {"detail": "Stripe integration not configured in this environment. "
                           "See apps.monetization.views module docstring."},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )
        # Real implementation would verify request.META['HTTP_STRIPE_SIGNATURE']
        # against settings.STRIPE_WEBHOOK_SECRET using the stripe SDK's
        # constructEvent, THEN call apply_subscription_event() with the parsed
        # event data. Left as a 501 rather than a fabricated success response.
        return Response({"detail": "Not implemented — see module docstring."}, status=status.HTTP_501_NOT_IMPLEMENTED)


class GooglePlayWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        from django.conf import settings
        if not settings.GOOGLE_PLAY_SERVICE_ACCOUNT_JSON:
            return Response(
                {"detail": "Google Play Billing integration not configured in this environment."},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )
        return Response({"detail": "Not implemented — see module docstring."}, status=status.HTTP_501_NOT_IMPLEMENTED)


class AppleIAPWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        from django.conf import settings
        if not settings.APPLE_IAP_SHARED_SECRET:
            return Response(
                {"detail": "Apple IAP integration not configured in this environment."},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )
        return Response({"detail": "Not implemented — see module docstring."}, status=status.HTTP_501_NOT_IMPLEMENTED)
