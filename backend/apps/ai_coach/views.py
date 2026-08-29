from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_coach.models import AICoachReport
from apps.ai_coach.serializers import AICoachReportSerializer


class AICoachReportListView(generics.ListAPIView):
    """§17 AI Coach — report history, most recent first. Gated by
    entitlements.ai_coach_available (§20: Pro/Family feature)."""
    serializer_class = AICoachReportSerializer

    def get_queryset(self):
        from apps.monetization.entitlements import resolve_entitlements
        entitlements = resolve_entitlements(self.request.user)
        if not entitlements.ai_coach_available:
            return AICoachReport.objects.none()
        return AICoachReport.objects.filter(user=self.request.user).order_by("-period_start")


class SmartLimitRecommendationView(APIView):
    """
    §18 Smart Limits. Explicitly NOT gated by ai_coach_available — per architecture
    doc §6, this is a baseline heuristic feature distinct from the Pro-gated AI
    Coach weekly narrative report above.
    """

    def get(self, request):
        from apps.ai_coach.recommender import HeuristicLimitRecommender

        package_name = request.query_params.get("package_name")
        if not package_name:
            return Response({"detail": "package_name query parameter is required."}, status=400)

        recommendation = HeuristicLimitRecommender().recommend(user=request.user, package_name=package_name)
        if recommendation is None:
            return Response({
                "package_name": package_name,
                "recommended_daily_minutes": 45,
                "based_on_days": 0,
                "rationale": "No usage history yet — showing a common default. "
                             "A personalized recommendation will appear after a few days of tracked usage.",
            })

        return Response({
            "package_name": recommendation.package_name,
            "recommended_daily_minutes": recommendation.recommended_daily_minutes,
            "based_on_days": recommendation.based_on_days,
            "rationale": recommendation.rationale,
        })


class AcceptSmartLimitRecommendationView(APIView):
    """
    §18: "Accept Recommendation" — turns the heuristic suggestion into a real
    AppLimit policy row, going through the SAME entitlement ceiling check as
    apps.policies.views.AppLimitListCreateView. This duplication (rather than
    delegating to that view) is deliberate: this endpoint's request shape
    (package_name + accepted recommended_minutes) differs from a generic AppLimit
    create, and the entitlement check itself is only two lines — worth keeping
    this endpoint self-contained and readable rather than reaching across apps
    for a thin wrapper.
    """

    def post(self, request):
        from apps.policies.models import AppLimit
        from apps.policies.serializers import AppLimitSerializer
        from apps.monetization.entitlements import resolve_entitlements
        from apps.core.models import write_audit_log, AuditLog

        package_name = request.data.get("package_name")
        display_name = request.data.get("display_name", package_name)
        daily_minutes = request.data.get("daily_minutes")

        if not package_name or daily_minutes is None:
            return Response({"detail": "package_name and daily_minutes are required."}, status=400)

        entitlements = resolve_entitlements(request.user)
        if not entitlements.daily_limit_allowed(int(daily_minutes)):
            return Response(
                {"detail": f"Your plan ({entitlements.plan_tier}) caps daily limits at {entitlements.max_daily_limit_minutes} minutes."},
                status=403,
            )

        limit, created = AppLimit.objects.update_or_create(
            user=request.user, package_name=package_name,
            defaults={"display_name": display_name, "daily_minutes": daily_minutes},
        )
        write_audit_log(
            AuditLog.EventType.POLICY_CREATED if created else AuditLog.EventType.POLICY_MODIFIED,
            actor=request.user, target=limit,
        )

        return Response(AppLimitSerializer(limit).data, status=201 if created else 200)
