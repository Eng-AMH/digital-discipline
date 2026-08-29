"""
Social views.

IMPLEMENTATION GAP, flagged honestly rather than glossed over: the consent
philosophy on apps.social.models.FamilyMember (guardian-controlled policy,
member cannot unilaterally escape enforcement) is enforced here for ROLE CHANGES
(see FamilyMemberRoleChangeView — only a guardian can promote/demote) and for
ADDING members (only a guardian can add). It is NOT yet enforced for a member
REMOVING THEMSELVES from a family group entirely, which would be the more
complete version of that guarantee (a member leaving the group could otherwise
sidestep a guardian-set hard lock by exiting the relationship). No
FamilyMemberDeleteView exists in this build. This gap is carried forward
explicitly into docs/03-REQUIREMENTS-AUDIT.md rather than silently left
unaddressed or falsely claimed as covered.
"""
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import write_audit_log, AuditLog
from apps.social.models import FriendRequest, AccountabilityLink, Challenge, ChallengeMember, FamilyGroup, FamilyMember
from apps.social.serializers import (
    FriendRequestSerializer, AccountabilityLinkSerializer, ChallengeSerializer,
    ChallengeMemberSerializer, LeagueEntrySerializer, FamilyGroupSerializer, FamilyMemberSerializer,
)


class FriendRequestListCreateView(generics.ListCreateAPIView):
    """§21 Friends."""
    serializer_class = FriendRequestSerializer

    def get_queryset(self):
        return FriendRequest.objects.filter(Q(from_user=self.request.user) | Q(to_user=self.request.user))

    def perform_create(self, serializer):
        serializer.save(from_user=self.request.user)


class FriendRequestDecideView(APIView):
    def post(self, request, request_id):
        friend_request = get_object_or_404(FriendRequest, id=request_id, to_user=request.user, status=FriendRequest.Status.PENDING)
        decision = request.data.get("decision")
        if decision not in ("accept", "decline"):
            return Response({"detail": "decision must be 'accept' or 'decline'"}, status=400)
        friend_request.status = FriendRequest.Status.ACCEPTED if decision == "accept" else FriendRequest.Status.DECLINED
        friend_request.save()
        return Response(FriendRequestSerializer(friend_request).data)


class AccountabilityLinkListCreateView(generics.ListCreateAPIView):
    """§25 Accountability Partner. Creating a link starts it PENDING — it only
    becomes usable as an UnlockRequest.approver once CONFIRMED by the partner
    (see AccountabilityLinkConfirmView), matching the blueprint's implication
    that this is a deliberate mutual relationship, not a unilateral designation."""
    serializer_class = AccountabilityLinkSerializer

    def get_queryset(self):
        return AccountabilityLink.objects.filter(Q(user=self.request.user) | Q(partner=self.request.user))

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AccountabilityLinkConfirmView(APIView):
    def post(self, request, link_id):
        link = get_object_or_404(AccountabilityLink, id=link_id, partner=request.user, status=AccountabilityLink.Status.PENDING)
        link.status = AccountabilityLink.Status.CONFIRMED
        link.save()
        return Response(AccountabilityLinkSerializer(link).data)


class ChallengeListCreateView(generics.ListCreateAPIView):
    """§23 Challenges."""
    serializer_class = ChallengeSerializer
    queryset = Challenge.objects.all().order_by("-start_date")

    def perform_create(self, serializer):
        challenge = serializer.save(created_by=self.request.user)
        ChallengeMember.objects.create(challenge=challenge, user=self.request.user)


class ChallengeJoinView(APIView):
    def post(self, request, challenge_id):
        challenge = get_object_or_404(Challenge, id=challenge_id)
        _, created = ChallengeMember.objects.get_or_create(challenge=challenge, user=request.user)
        if not created:
            return Response({"detail": "Already a member of this challenge."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_201_CREATED)


class ChallengeMembersView(generics.ListAPIView):
    """§23: "كل شخص يرى: Focus Score, Streak, Screen Time, Challenge Progress" —
    serializer computes these live per member, see ChallengeMemberSerializer."""
    serializer_class = ChallengeMemberSerializer

    def get_queryset(self):
        return ChallengeMember.objects.filter(challenge_id=self.kwargs["challenge_id"]).select_related("user")


class FocusLeagueView(APIView):
    """
    §24 Focus League. Deliberately a computed read-model, not a stored
    leaderboard table (see LeagueEntrySerializer docstring) — this endpoint
    ranks by the CURRENT WEEK's FocusScoreSnapshot average, scoped to FRIENDS
    (derived from the requester's accepted FriendRequest graph),
    UNIVERSITY (organization_key match), or GLOBAL (top N overall).
    """

    def get(self, request):
        scope = request.query_params.get("scope", "FRIENDS")
        from apps.gamification.models import FocusScoreSnapshot
        from django.db.models import Avg
        from apps.accounts.models import User

        today = timezone.now().date()
        week_start = today - timezone.timedelta(days=today.weekday())

        if scope == "FRIENDS":
            friend_ids = set(
                FriendRequest.objects.filter(from_user=request.user, status=FriendRequest.Status.ACCEPTED).values_list("to_user_id", flat=True)
            ) | set(
                FriendRequest.objects.filter(to_user=request.user, status=FriendRequest.Status.ACCEPTED).values_list("from_user_id", flat=True)
            )
            friend_ids.add(request.user.id)
            candidate_user_ids = friend_ids
        elif scope == "GLOBAL":
            candidate_user_ids = None  # no filter — all users
        else:
            return Response({"detail": "UNIVERSITY scope requires an organization_key — not available without Organization API in this phase."}, status=400)

        qs = FocusScoreSnapshot.objects.filter(date__gte=week_start)
        if candidate_user_ids is not None:
            qs = qs.filter(user_id__in=candidate_user_ids)

        rankings = (
            qs.values("user_id", "user__display_name", "user__email")
            .annotate(avg_score=Avg("score"))
            .order_by("-avg_score")[:50]
        )

        entries = [
            {
                "user_id": row["user_id"],
                "display_name": row["user__display_name"] or row["user__email"],
                "score": round(row["avg_score"]),
                "rank": idx + 1,
            }
            for idx, row in enumerate(rankings)
        ]
        return Response(LeagueEntrySerializer(entries, many=True).data)


class FamilyGroupListCreateView(generics.ListCreateAPIView):
    """§27 Family."""
    serializer_class = FamilyGroupSerializer

    def get_queryset(self):
        return FamilyGroup.objects.filter(members__user=self.request.user).distinct()

    def perform_create(self, serializer):
        group = serializer.save(created_by=self.request.user)
        FamilyMember.objects.create(family_group=group, user=self.request.user, role=FamilyMember.Role.GUARDIAN)
        write_audit_log(AuditLog.EventType.FAMILY_MEMBER_ADDED, actor=self.request.user, target=group)


class FamilyMemberListCreateView(generics.ListCreateAPIView):
    """Adding a member requires the requester to already be a GUARDIAN of this
    group — enforced in perform_create, not just implied by the frontend."""
    serializer_class = FamilyMemberSerializer

    def get_queryset(self):
        return FamilyMember.objects.filter(family_group_id=self.kwargs["family_group_id"])

    def perform_create(self, serializer):
        family_group = get_object_or_404(FamilyGroup, id=self.kwargs["family_group_id"])
        is_guardian = FamilyMember.objects.filter(
            family_group=family_group, user=self.request.user, role=FamilyMember.Role.GUARDIAN
        ).exists()
        if not is_guardian:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only a guardian can add family members.")
        member = serializer.save(family_group=family_group)
        write_audit_log(AuditLog.EventType.FAMILY_MEMBER_ADDED, actor=self.request.user, target=member)


class FamilyMemberRoleChangeView(APIView):
    """
    Guardian-only. This is the enforcement point of the consent philosophy: a
    MEMBER can never promote themselves to GUARDIAN or change another member's
    role — only an existing GUARDIAN can, and every change is audited (§9's
    "care not punishment" is structural here, not just a policy statement).
    """

    def post(self, request, family_group_id, member_id):
        requesting_membership = get_object_or_404(FamilyMember, family_group_id=family_group_id, user=request.user, role=FamilyMember.Role.GUARDIAN)
        target_member = get_object_or_404(FamilyMember, id=member_id, family_group_id=family_group_id)

        new_role = request.data.get("role")
        if new_role not in dict(FamilyMember.Role.choices):
            return Response({"detail": "Invalid role."}, status=400)

        old_role = target_member.role
        target_member.role = new_role
        target_member.save()

        write_audit_log(
            AuditLog.EventType.FAMILY_PERMISSION_CHANGED, actor=request.user, target=target_member,
            metadata={"old_role": old_role, "new_role": new_role},
        )
        return Response(FamilyMemberSerializer(target_member).data)
