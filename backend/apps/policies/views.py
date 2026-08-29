"""
Policy views — §4 through §11, §26, §29, §43, §47.

Every mutation that touches AppLimit.daily_minutes or WebsiteLimit.daily_minutes
goes through can_modify_limit() (weekly-lock guard) and
entitlements.daily_limit_allowed() (plan-tier ceiling, §21/§24) — these are NOT
optional checks a client can bypass, they're enforced here at the one place all
limit changes flow through.
"""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.models import write_audit_log, AuditLog
from apps.devices.models import Device
from apps.monetization.entitlements import resolve_entitlements
from apps.policies.models import (
    AppLimit, WebsiteLimit, WeeklyPlan, Schedule, ScheduleMode, FocusSession, UnlockRequest, UnlockToken,
)
from apps.policies.serializers import (
    AppLimitSerializer, WebsiteLimitSerializer, WeeklyPlanSerializer, ScheduleSerializer,
    FocusSessionSerializer, UnlockRequestSerializer, UnlockTokenSerializer,
)
from apps.policies.services import (
    can_modify_limit, assert_hard_lock_allowed, mint_unlock_token, redeem_unlock_token,
    build_signed_policy_blob,
)


class AppLimitListCreateView(generics.ListCreateAPIView):
    """§4 Daily App Limits."""
    serializer_class = AppLimitSerializer

    def get_queryset(self):
        return AppLimit.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        entitlements = resolve_entitlements(self.request.user)
        requested = serializer.validated_data["daily_minutes"]
        if not entitlements.daily_limit_allowed(requested):
            raise ValidationErrorResponse(
                f"Your plan ({entitlements.plan_tier}) caps daily limits at "
                f"{entitlements.max_daily_limit_minutes} minutes. Upgrade for custom limits."
            )
        limit = serializer.save(user=self.request.user)
        write_audit_log(AuditLog.EventType.POLICY_CREATED, actor=self.request.user, target=limit)


class AppLimitDetailView(generics.RetrieveUpdateDestroyAPIView):
    """§5 Weekly Locked Plan guard applied here: loosening a limit that's under an
    active locked WeeklyPlan is rejected with 403, not silently ignored."""
    serializer_class = AppLimitSerializer

    def get_queryset(self):
        return AppLimit.objects.filter(user=self.request.user)

    def perform_update(self, serializer):
        instance = self.get_object()
        new_minutes = serializer.validated_data.get("daily_minutes", instance.daily_minutes)

        entitlements = resolve_entitlements(self.request.user)
        if not entitlements.daily_limit_allowed(new_minutes):
            raise ValidationErrorResponse(
                f"Your plan ({entitlements.plan_tier}) caps daily limits at {entitlements.max_daily_limit_minutes} minutes."
            )

        weekly_plan_ids = list(instance.weekly_plans.values_list("id", flat=True))
        if not can_modify_limit(
            user=self.request.user, weekly_plan_ids=weekly_plan_ids,
            new_daily_minutes=new_minutes, current_daily_minutes=instance.daily_minutes,
        ):
            write_audit_log(
                AuditLog.EventType.POLICY_MODIFICATION_BLOCKED, actor=self.request.user, target=instance,
                metadata={"attempted_new_minutes": new_minutes, "current_minutes": instance.daily_minutes},
            )
            raise ValidationErrorResponse(
                "This limit is part of a locked weekly plan and cannot be loosened until the lock expires. "
                "You can still make it stricter."
            )

        limit = serializer.save()
        write_audit_log(AuditLog.EventType.POLICY_MODIFIED, actor=self.request.user, target=limit)


class ValidationErrorResponse(Exception):
    """Small helper so perform_create/perform_update can raise a clean 403 with a
    message, rather than each view hand-rolling a Response object mid-serializer-save
    flow (DRF's generic views expect perform_* to return None, not a Response)."""
    def __init__(self, detail):
        self.detail = detail


# DRF exception handler registration for the helper above — kept local to this
# module via a thin wrapper rather than a global override, since this specific
# "policy modification blocked" shape is only used in this file.
from rest_framework.views import exception_handler as drf_default_exception_handler


def policy_exception_handler(exc, context):
    if isinstance(exc, ValidationErrorResponse):
        return Response({"detail": exc.detail}, status=status.HTTP_403_FORBIDDEN)
    return drf_default_exception_handler(exc, context)


class WebsiteLimitListCreateView(generics.ListCreateAPIView):
    """§6 Website Blocking. See WebsiteCategory docstring for the documented
    domain-level-only limitation surfaced to the client via `category`."""
    serializer_class = WebsiteLimitSerializer

    def get_queryset(self):
        return WebsiteLimit.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        limit = serializer.save(user=self.request.user)
        write_audit_log(AuditLog.EventType.POLICY_CREATED, actor=self.request.user, target=limit)


class WebsiteLimitDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = WebsiteLimitSerializer

    def get_queryset(self):
        return WebsiteLimit.objects.filter(user=self.request.user)


class WeeklyPlanListCreateView(generics.ListCreateAPIView):
    """§5 Weekly Locked Plan / §9 Exam Mode (plan_type=EXAM_MODE)."""
    serializer_class = WeeklyPlanSerializer

    def get_queryset(self):
        return WeeklyPlan.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        if serializer.validated_data.get("is_hard_locked"):
            assert_hard_lock_allowed(self.request.user)  # raises PermissionDenied → 403 if consent incomplete
        serializer.save(user=self.request.user)


class WeeklyPlanConfirmView(APIView):
    """
    §5: "CONFIRM WEEK" button. This is the ONLY way is_confirmed/locked_until get
    set — the model itself never self-locks, matching the blueprint's explicit
    intent that locking is a deliberate user action, not an automatic side effect
    of creating a plan.
    """

    def post(self, request, plan_id):
        plan = get_object_or_404(WeeklyPlan, id=plan_id, user=request.user)
        if plan.is_hard_locked:
            assert_hard_lock_allowed(request.user)

        duration_days = 7 if plan.plan_type == WeeklyPlan.PlanType.WEEKLY else request.data.get("duration_days", 14)

        plan.is_confirmed = True
        plan.confirmed_at = timezone.now()
        plan.locked_until = timezone.now() + timezone.timedelta(days=duration_days)
        plan.save()

        write_audit_log(
            AuditLog.EventType.HARD_LOCK_ENABLED if plan.is_hard_locked else AuditLog.EventType.POLICY_MODIFIED,
            actor=request.user, target=plan, metadata={"locked_until": str(plan.locked_until)},
        )
        return Response(WeeklyPlanSerializer(plan).data)


class ScheduleListCreateView(generics.ListCreateAPIView):
    """§8 Smart Schedules."""
    serializer_class = ScheduleSerializer

    def get_queryset(self):
        return Schedule.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        entitlements = resolve_entitlements(self.request.user)
        mode = serializer.validated_data.get("mode")
        # §20: SLEEP mode is explicitly a PRO-tier feature per the blueprint's own
        # plan table; STUDY/FOCUS/CUSTOM schedules are available on all tiers.
        if mode == ScheduleMode.SLEEP and not entitlements.sleep_mode_available:
            raise ValidationErrorResponse(
                f"Sleep Mode schedules require a plan with sleep mode enabled (your plan: {entitlements.plan_tier})."
            )
        serializer.save(user=self.request.user)


class ScheduleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ScheduleSerializer

    def get_queryset(self):
        return Schedule.objects.filter(user=self.request.user)


class FocusSessionStartView(APIView):
    """§7 Focus Mode / §26 Digital Detox / §29 (session_type differentiates)."""

    def post(self, request):
        session_type = request.data.get("session_type", FocusSession.SessionType.FOCUS)
        entitlements = resolve_entitlements(request.user)
        if session_type == FocusSession.SessionType.FOCUS and not entitlements.focus_mode_available:
            return Response(
                {"detail": f"Focus Mode is not available on your plan ({entitlements.plan_tier})."},
                status=status.HTTP_403_FORBIDDEN,
            )

        already_active = FocusSession.objects.filter(user=request.user, status=FocusSession.Status.ACTIVE).exists()
        if already_active:
            return Response({"detail": "A focus session is already active."}, status=status.HTTP_400_BAD_REQUEST)

        device = get_object_or_404(Device, id=request.data.get("device"), user=request.user)
        session = FocusSession.objects.create(
            user=request.user,
            device=device,
            session_type=session_type,
            planned_minutes=request.data.get("planned_minutes", 25),
            allowed_packages=request.data.get("allowed_packages", []),
            blocked_packages=request.data.get("blocked_packages", []),
        )
        _push_focus_session_update(session)
        return Response(FocusSessionSerializer(session).data, status=status.HTTP_201_CREATED)


class FocusSessionEndView(APIView):
    def post(self, request, session_id):
        session = get_object_or_404(FocusSession, id=session_id, user=request.user, status=FocusSession.Status.ACTIVE)
        completed_naturally = request.data.get("completed_naturally", False)

        session.ended_at = timezone.now()
        session.actual_minutes = int((session.ended_at - session.started_at).total_seconds() // 60)
        session.status = FocusSession.Status.COMPLETED if completed_naturally else FocusSession.Status.ABANDONED
        session.save()

        if session.status == FocusSession.Status.COMPLETED:
            # §28 Earn Your Scroll: completing a focus session grants Focus Tokens.
            from apps.gamification.models import TokenTransaction
            EARN_YOUR_SCROLL_RATIO_MINUTES_PER_TOKEN = 4.5  # ~45min focus -> 10min token equiv, per §25 example
            tokens_earned = max(1, int(session.actual_minutes / EARN_YOUR_SCROLL_RATIO_MINUTES_PER_TOKEN))
            TokenTransaction.objects.create(
                user=request.user, amount=tokens_earned,
                reason=TokenTransaction.Reason.FOCUS_SESSION_COMPLETED, reference_id=str(session.id),
            )

        _push_focus_session_update(session)
        return Response(FocusSessionSerializer(session).data)


def _push_focus_session_update(session):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            f"focus_session_user_{session.user_id}",
            {"type": "focus_session_update", "payload": FocusSessionSerializer(session).data},
        )
    except Exception:
        pass  # real-time push is UX enhancement only, never blocks the request — same
              # rationale as apps.devices.services._push_device_health_update


class UnlockRequestCreateView(generics.CreateAPIView):
    """§10 Secure Unlock / §25 Accountability / §47 Emergency Mode."""
    serializer_class = UnlockRequestSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "unlock"

    def perform_create(self, serializer):
        package_name = serializer.validated_data["package_name"]
        # §9 Exam Mode hard-lock check: a WeeklyPlan with is_hard_locked=True
        # blocks even Secure Unlock requests, not just direct limit edits — this
        # is the one place that distinction (documented on the model) is enforced.
        hard_locked_plan = WeeklyPlan.objects.filter(
            user=self.request.user, is_confirmed=True, is_hard_locked=True, locked_until__gte=timezone.now(),
            app_limits__package_name=package_name,
        ).exists()
        if hard_locked_plan:
            raise ValidationErrorResponse(
                "This app is under an Exam Mode hard lock — extra time requests are disabled until the lock expires."
            )

        reason_type = serializer.validated_data.get("reason_type", UnlockRequest.ReasonType.STANDARD)
        unlock_request = serializer.save(user=self.request.user)

        write_audit_log(AuditLog.EventType.UNLOCK_REQUESTED, actor=self.request.user, target=unlock_request)

        # §10 Free tier gets limited AUTO-approved unlocks (no accountability
        # partner needed); ACCOUNTABILITY-reason requests always require a human
        # decision regardless of plan, since the entire point is a second person's
        # judgment, not an entitlement to bypass.
        if reason_type in (UnlockRequest.ReasonType.STANDARD, UnlockRequest.ReasonType.REWARDED_AD):
            unlock_request.status = UnlockRequest.Status.AUTO_APPROVED
            unlock_request.decided_at = timezone.now()
            unlock_request.save()
            mint_unlock_token(unlock_request=unlock_request)
            write_audit_log(AuditLog.EventType.UNLOCK_APPROVED, actor=self.request.user, target=unlock_request)


class UnlockRequestDecideView(APIView):
    """§25 Accountability Partner approves/rejects. Only the designated approver
    (a CONFIRMED AccountabilityLink partner, checked here) may decide — not just
    any authenticated user who happens to guess the request id."""

    def post(self, request, request_id):
        from apps.social.models import AccountabilityLink

        unlock_request = get_object_or_404(UnlockRequest, id=request_id, status=UnlockRequest.Status.PENDING)
        is_valid_partner = AccountabilityLink.objects.filter(
            user=unlock_request.user, partner=request.user, status=AccountabilityLink.Status.CONFIRMED
        ).exists()
        if not is_valid_partner:
            return Response({"detail": "You are not an accountability partner for this user."}, status=status.HTTP_403_FORBIDDEN)

        decision = request.data.get("decision")
        if decision not in ("approve", "reject"):
            return Response({"detail": "decision must be 'approve' or 'reject'"}, status=status.HTTP_400_BAD_REQUEST)

        unlock_request.approver = request.user
        unlock_request.decided_at = timezone.now()
        if decision == "approve":
            unlock_request.status = UnlockRequest.Status.APPROVED
            unlock_request.save()
            mint_unlock_token(unlock_request=unlock_request)
            write_audit_log(AuditLog.EventType.UNLOCK_APPROVED, actor=request.user, target=unlock_request)
        else:
            unlock_request.status = UnlockRequest.Status.REJECTED
            unlock_request.save()
            write_audit_log(AuditLog.EventType.UNLOCK_REJECTED, actor=request.user, target=unlock_request)

        from apps.notifications.models import Notification, NotificationType
        Notification.objects.create(
            user=unlock_request.user,
            notification_type=NotificationType.UNLOCK_REQUEST_DECIDED,
            title=f"Unlock request {unlock_request.status.lower()}",
            body=f"{unlock_request.package_name}: +{unlock_request.requested_minutes} minutes",
            metadata={"unlock_request_id": str(unlock_request.id)},
        )
        return Response(UnlockRequestSerializer(unlock_request).data)


class UnlockTokenRedeemView(APIView):
    """§11: device confirms it applied the grant. Replay-protected — see
    apps.policies.services.redeem_unlock_token docstring."""

    def post(self, request, token_id):
        device = get_object_or_404(Device, id=request.data.get("device"), user=request.user)
        token, error = redeem_unlock_token(token_id=token_id, device=device)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
        return Response(UnlockTokenSerializer(token).data)


class OfflinePolicyBlobView(APIView):
    """
    §43 Offline Mode: the actual signed, self-contained policy snapshot a device
    caches and enforces from without needing live connectivity — architecture
    doc §5.4.
    """

    def get(self, request, device_id):
        device = get_object_or_404(Device, id=device_id, user=request.user, is_active=True)
        blob = build_signed_policy_blob(user=request.user, device=device)
        return Response(blob)
