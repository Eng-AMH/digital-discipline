"""
Social: §22 Accountability Partner, §23 Challenges, §24 Focus League, §27 Family.

Design decision (architecture doc §9): FamilyMember has explicit roles, and the
platform's own stated philosophy ("care not punishment," blueprint §56) is enforced
structurally — a minor member cannot remove a guardian-set policy (checked in
apps.policies views via FamilyMember.role), but a guardian is ALWAYS reachable to
adjust it. This avoids building a system where a minor gets hard-locked out with
literally no recourse, which the blueprint's own philosophy section argues against.
"""
from django.db import models

from apps.core.models import TimestampedModel, UUIDModel


class FriendRequest(UUIDModel, TimestampedModel):
    """§21 Friends — the request/accept flow underlying Challenges and Focus League."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        DECLINED = "DECLINED", "Declined"

    from_user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="friend_requests_sent")
    to_user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="friend_requests_received")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["from_user", "to_user"], name="unique_friend_request_pair"),
        ]


class AccountabilityLink(UUIDModel, TimestampedModel):
    """
    §25 Accountability Partner. A CONFIRMED, mutual relationship — required before
    `partner` can appear as `UnlockRequest.approver` in apps.policies. Modeled
    separately from FriendRequest because being a friend and being an accountability
    partner (someone who can approve/reject YOUR unlock requests) are meaningfully
    different trust levels; conflating them would let any accepted friend silently
    gain approval power.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        REVOKED = "REVOKED", "Revoked"

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="accountability_partners_of")
    partner = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="accountability_partner_for")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "partner"], name="unique_accountability_pair"),
        ]


class Challenge(UUIDModel, TimestampedModel):
    """§23 Challenges, e.g. '30 Day Digital Detox' with named participants."""

    class Status(models.TextChoices):
        UPCOMING = "UPCOMING", "Upcoming"
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"

    created_by = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="challenges_created")
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True)
    duration_days = models.PositiveIntegerField()
    start_date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UPCOMING)
    token_reward = models.PositiveIntegerField(default=0, help_text="§18 Focus Tokens granted on completion")

    @property
    def end_date(self):
        from datetime import timedelta
        return self.start_date + timedelta(days=self.duration_days)


class ChallengeMember(UUIDModel, TimestampedModel):
    """Per-member progress within a Challenge — Focus Score/Streak/Screen Time are
    READ from the member's own FocusScoreSnapshot/Streak rows (apps.gamification),
    not duplicated here, so there is exactly one source of truth for those numbers."""

    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="challenge_memberships")
    joined_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["challenge", "user"], name="unique_challenge_member"),
        ]


class League(UUIDModel, TimestampedModel):
    """§24 Focus League — Friends/University/Global scopes."""

    class Scope(models.TextChoices):
        FRIENDS = "FRIENDS", "Friends League"
        UNIVERSITY = "UNIVERSITY", "University League"
        GLOBAL = "GLOBAL", "Global League"

    scope = models.CharField(max_length=16, choices=Scope.choices)
    # For FRIENDS scope, this is null and membership is derived from the requesting
    # user's FriendRequest graph at query time — no need to materialize a friends-only
    # league per user. For UNIVERSITY scope, this groups by an org identifier.
    owner_user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, null=True, blank=True, related_name="owned_leagues"
    )
    organization_key = models.CharField(max_length=100, blank=True)
    week_number = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()

    class Meta:
        indexes = [models.Index(fields=["scope", "year", "week_number"])]


class FamilyGroup(UUIDModel, TimestampedModel):
    """§27 Family — a household unit."""

    name = models.CharField(max_length=100, default="My Family")
    created_by = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="family_groups_created")


class FamilyMember(UUIDModel, TimestampedModel):
    """
    Per-user role within a FamilyGroup. See module docstring for the consent
    philosophy this structurally enforces via `role`.
    """

    class Role(models.TextChoices):
        GUARDIAN = "GUARDIAN", "Guardian (can set/adjust any member's policy)"
        MEMBER = "MEMBER", "Member (policy set by a guardian, cannot self-loosen hard locks)"

    family_group = models.ForeignKey(FamilyGroup, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="family_memberships")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    # §41 Privacy Center principle applied to Family specifically: a guardian sees
    # aggregate/policy-relevant data (Focus Score, limit breaches), NOT a live feed
    # of exactly which apps were opened when — this flag exists so that boundary is
    # an explicit, auditable setting rather than an implicit "guardians see everything."
    detailed_activity_visible_to_guardians = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["family_group", "user"], name="unique_family_membership"),
        ]
