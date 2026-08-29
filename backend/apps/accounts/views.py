"""
Accounts views.

Onboarding progression endpoints are the ACTUAL implementation of the consent gate
described in architecture doc §9 — `explain_permissions` and `give_consent` are the
only way `OnboardingState.permissions_explained_at`/`consent_given_at` get set, and
apps.policies checks those fields server-side before allowing any HARD_LOCK policy.
There is no way to skip this from the API layer.
"""
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import OnboardingState, UserGoal
from apps.accounts.serializers import (
    RegisterSerializer, UserSerializer, OnboardingStateSerializer, UserGoalSerializer,
)
from apps.core.models import write_audit_log, AuditLog

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        write_audit_log(AuditLog.EventType.LOGIN_SUCCESS, actor=user, metadata={"event": "registration"})
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class OnboardingStateView(generics.RetrieveAPIView):
    serializer_class = OnboardingStateSerializer

    def get_object(self):
        state, _ = OnboardingState.objects.get_or_create(user=self.request.user)
        return state


@api_view(["POST"])
def advance_onboarding_step(request):
    """
    §38 Onboarding step progression. Body: {"step": "GOALS_CHOSEN"}. Generic
    step-advance for the non-consent steps (account created → goals → apps →
    limits → weekly-lock-decision) — the two CONSENT-SPECIFIC steps below have
    their own dedicated endpoints because they carry real legal/product weight
    and shouldn't be settable via a generic "set any step" call.
    """
    step = request.data.get("step")
    valid_steps = [choice[0] for choice in OnboardingState.Step.choices]
    if step not in valid_steps:
        return Response({"detail": f"Invalid step. Must be one of {valid_steps}"}, status=400)
    if step in (OnboardingState.Step.PERMISSIONS_EXPLAINED, OnboardingState.Step.POLICY_CONFIRMED):
        return Response(
            {"detail": "Use the dedicated /onboarding/explain-permissions/ or /onboarding/give-consent/ endpoints for consent steps."},
            status=400,
        )

    state, _ = OnboardingState.objects.get_or_create(user=request.user)
    state.current_step = step
    if step == OnboardingState.Step.COMPLETE:
        state.completed_at = timezone.now()
    state.save()
    return Response(OnboardingStateSerializer(state).data)


@api_view(["POST"])
def explain_permissions(request):
    """
    §38: "توضيح الصلاحيات" (permissions explained). This endpoint is called ONLY
    after the client has actually shown the permissions-explanation screen — the
    backend trusts the client on WHEN this is called, but the mere existence of
    this timestamp is what apps.policies.services.assert_hard_lock_allowed checks,
    so a client that never shows the explanation screen also never unlocks
    hard-lock policies for that user.
    """
    state, _ = OnboardingState.objects.get_or_create(user=request.user)
    state.permissions_explained_at = timezone.now()
    state.current_step = OnboardingState.Step.PERMISSIONS_EXPLAINED
    state.save()
    return Response(OnboardingStateSerializer(state).data)


@api_view(["POST"])
def give_consent(request):
    """§38: "موافقة واضحة" (clear consent). See explain_permissions docstring —
    same trust model, same downstream enforcement in apps.policies.services."""
    state, _ = OnboardingState.objects.get_or_create(user=request.user)
    if state.permissions_explained_at is None:
        return Response(
            {"detail": "Permissions must be explained before consent can be given."}, status=400
        )
    state.consent_given_at = timezone.now()
    state.current_step = OnboardingState.Step.POLICY_CONFIRMED
    state.save()

    write_audit_log(AuditLog.EventType.POLICY_CREATED, actor=request.user, metadata={"event": "hard_lock_consent_given"})
    return Response(OnboardingStateSerializer(state).data)


class UserGoalListCreateView(generics.ListCreateAPIView):
    """§42/§45 Personal Goals."""
    serializer_class = UserGoalSerializer

    def get_queryset(self):
        return UserGoal.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class UserGoalDeleteView(generics.DestroyAPIView):
    serializer_class = UserGoalSerializer

    def get_queryset(self):
        return UserGoal.objects.filter(user=self.request.user)


class AccountExportView(APIView):
    """
    §41 Privacy Center: "كيفية تصدير بيانات المستخدم." Real export of the user's
    own data — not a stub. Kept intentionally flat/simple (a dict of querysets
    serialized to JSON) rather than a fancy async job system, since for an
    individual user's data volume this completes well within a normal request
    timeout; a Celery-based async export would be the right upgrade only once
    data volume actually requires it.
    """

    def get(self, request):
        user = request.user
        from apps.devices.models import Device, ActivityLog
        from apps.policies.models import AppLimit, WebsiteLimit
        from apps.gamification.models import FocusScoreSnapshot, TokenTransaction

        token_balance = TokenTransaction.objects.filter(user=user).aggregate(balance=Sum("amount"))["balance"] or 0

        data = {
            "profile": UserSerializer(user).data,
            "devices": list(Device.objects.filter(user=user).values(
                "id", "name", "platform", "created_at", "last_heartbeat_at"
            )),
            "app_limits": list(AppLimit.objects.filter(user=user).values(
                "package_name", "display_name", "daily_minutes"
            )),
            "website_limits": list(WebsiteLimit.objects.filter(user=user).values("domain", "daily_minutes")),
            "focus_scores": list(FocusScoreSnapshot.objects.filter(user=user).values("date", "score")),
            "token_balance": token_balance,
            "activity_summary_days": ActivityLog.objects.filter(user=user).values("occurred_date").distinct().count(),
        }

        write_audit_log(AuditLog.EventType.ACCOUNT_EXPORTED, actor=user, ip_address=request.META.get("REMOTE_ADDR"))
        return Response(data)


class AccountDeleteView(APIView):
    """
    §41 Privacy Center: "كيفية حذف الحساب." Soft-delete with a window (see
    User.deletion_requested_at docstring) rather than immediate hard delete —
    real deletion is performed by a separate Celery task after the window closes
    (not built in this phase; the request-recording half is real and complete).
    """

    def post(self, request):
        user = request.user
        user.deletion_requested_at = timezone.now()
        user.is_active = False
        user.save(update_fields=["deletion_requested_at", "is_active"])

        write_audit_log(AuditLog.EventType.ACCOUNT_DELETED, actor=user, ip_address=request.META.get("REMOTE_ADDR"))
        return Response({"detail": "Account deletion requested. Your account has been deactivated."})
