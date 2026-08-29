"""
Monetization: §20 Subscription Plans, §21 Extended Limits (enforced via
EntitlementResolver, see services.py), §32 Referral System, §33 Affiliate/Ambassador,
§30 Cosmetic Store, §31/§32 Schools/Companies (Organization, forward-compat only).

Design decision (architecture doc §7): subscription STATE (active/canceled/expired)
is owned by our backend regardless of which storefront originated it (Web/Google
Play/Apple) — Subscription.source records provenance but never gates behavior;
Subscription.status is the only thing EntitlementResolver reads. This is the direct
implementation of blueprint §47's explicit "Backend هو مصدر الحقيقة."
"""
from django.db import models

from apps.core.models import TimestampedModel, UUIDModel


class Plan(UUIDModel):
    """§20 Subscription Plans catalog: FREE / PRO / FAMILY. A catalog table (not a
    hardcoded enum) so pricing/limits can be adjusted without a code deploy, and so
    EntitlementResolver has one place to read plan-level defaults from."""

    class Tier(models.TextChoices):
        FREE = "FREE", "Free"
        PRO = "PRO", "Pro"
        FAMILY = "FAMILY", "Family"

    tier = models.CharField(max_length=16, choices=Tier.choices, unique=True)
    display_name = models.CharField(max_length=50)
    monthly_price_cents = models.PositiveIntegerField(default=0)
    max_devices = models.PositiveSmallIntegerField(default=1)
    max_daily_limit_minutes = models.PositiveIntegerField(
        default=60, help_text="§21 Extended Limits ceiling — e.g. Free capped at 60m, Pro unlimited (0=unlimited)"
    )
    weekly_lock_available = models.BooleanField(default=True)
    focus_mode_available = models.BooleanField(default=True)
    sleep_mode_available = models.BooleanField(default=False)
    ai_coach_available = models.BooleanField(default=False)
    ads_enabled = models.BooleanField(default=True)
    family_features_available = models.BooleanField(default=False)


class Subscription(UUIDModel, TimestampedModel):
    """See module docstring — status is the single source of truth regardless of
    which storefront originated the purchase."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        GRACE_PERIOD = "GRACE_PERIOD", "Grace period (payment failed, retrying)"
        CANCELED = "CANCELED", "Canceled (active until period end)"
        EXPIRED = "EXPIRED", "Expired"

    class Source(models.TextChoices):
        WEB_STRIPE = "WEB_STRIPE", "Web (Stripe)"
        GOOGLE_PLAY = "GOOGLE_PLAY", "Google Play Billing"
        APPLE_IAP = "APPLE_IAP", "Apple In-App Purchase"
        PROMOTIONAL = "PROMOTIONAL", "Promotional/comped (referral rewards, etc.)"

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    source = models.CharField(max_length=16, choices=Source.choices)
    external_reference_id = models.CharField(
        max_length=255, blank=True, help_text="Stripe subscription id / Play purchase token / Apple original tx id"
    )
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "status"])]


class FamilyGroupSubscription(UUIDModel):
    """§20 FAMILY plan covers multiple accounts under one subscription — links a
    Subscription (billed to one payer) to the FamilyGroup it covers."""

    subscription = models.OneToOneField(Subscription, on_delete=models.CASCADE, related_name="family_coverage")
    family_group = models.ForeignKey("social.FamilyGroup", on_delete=models.CASCADE, related_name="subscription_coverage")


class StoreItem(UUIDModel):
    """§30 Cosmetic Store — explicitly non-restriction-affecting items."""

    class Category(models.TextChoices):
        THEME = "THEME", "Theme"
        PROFILE_FRAME = "PROFILE_FRAME", "Profile Frame"
        BADGE = "BADGE", "Badge"
        DASHBOARD_EFFECT = "DASHBOARD_EFFECT", "Dashboard Effect"
        ANIMATION = "ANIMATION", "Special Animation"

    category = models.CharField(max_length=20, choices=Category.choices)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=280, blank=True)
    token_price = models.PositiveIntegerField(null=True, blank=True, help_text="Null = not purchasable with tokens")
    real_money_price_cents = models.PositiveIntegerField(null=True, blank=True, help_text="Null = not purchasable with real money")
    requires_plan_tier = models.CharField(max_length=16, choices=Plan.Tier.choices, blank=True)


class UserInventory(UUIDModel):
    """Owned StoreItems + which one is currently equipped, per category."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="inventory")
    item = models.ForeignKey(StoreItem, on_delete=models.CASCADE, related_name="owners")
    acquired_at = models.DateTimeField(auto_now_add=True)
    is_equipped = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "item"], name="unique_user_inventory_item"),
        ]


class ReferralCode(UUIDModel, TimestampedModel):
    """§32 Referral System. One code per user, human-readable per the blueprint's
    own example (focus.app/r/AMMAR123)."""

    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="referral_code")
    code = models.CharField(max_length=20, unique=True)


class Referral(UUIDModel, TimestampedModel):
    """
    A single referred signup. Design decision (architecture doc §10): reward is
    granted only once `qualified_at` is set by a Celery check confirming REAL usage
    (see apps.monetization.tasks.check_referral_qualification) — NOT at signup —
    which structurally blocks the "50 empty accounts" attack the blueprint names in
    §39. `status` tracks this lifecycle explicitly so it's visible/auditable, not
    inferred from other fields.
    """

    class Status(models.TextChoices):
        SIGNED_UP = "SIGNED_UP", "Signed up (unqualified)"
        QUALIFIED = "QUALIFIED", "Qualified (reward granted)"
        REJECTED_FRAUD = "REJECTED_FRAUD", "Rejected — suspected fraud"

    referrer = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="referrals_made")
    referred_user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="referred_by")
    code_used = models.CharField(max_length=20)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SIGNED_UP)
    qualified_at = models.DateTimeField(null=True, blank=True)
    reward_granted_days = models.PositiveIntegerField(null=True, blank=True, help_text="Pro days granted, per tier table")

    # Anti-abuse signals captured at signup time for later fraud review — see
    # architecture §10. Kept minimal (device public key fingerprint hash, not raw
    # PII) to stay consistent with §41 data-minimization.
    referred_device_public_key_hash = models.CharField(max_length=128, blank=True)

    class Meta:
        indexes = [models.Index(fields=["referrer", "status"])]


class AmbassadorAccount(UUIDModel, TimestampedModel):
    """§33 Affiliate/Ambassador Program — a User opted into a commission-bearing
    referral relationship, distinct from the standard §32 friend-referral rewards."""

    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="ambassador_account")
    commission_rate_percent = models.PositiveSmallIntegerField(default=20)
    is_active = models.BooleanField(default=True)


class CommissionLedgerEntry(UUIDModel):
    """Ledger, same audit-safe pattern as TokenTransaction — never a mutable balance."""

    ambassador = models.ForeignKey(AmbassadorAccount, on_delete=models.CASCADE, related_name="commission_entries")
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, related_name="commission_entries")
    amount_cents = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class Organization(UUIDModel, TimestampedModel):
    """
    §28 Schools/Institutions, §29 Companies/Teams — forward-compatible model only,
    per architecture doc §0.2: the blueprint itself frames these as V4/enterprise
    phases, so this ships as a real schema with no dedicated API surface yet, rather
    than either building unneeded scope or leaving zero path forward.
    """

    class OrgType(models.TextChoices):
        SCHOOL = "SCHOOL", "School / Institution"
        COMPANY = "COMPANY", "Company / Team"

    org_type = models.CharField(max_length=16, choices=OrgType.choices)
    name = models.CharField(max_length=200)
    admin_user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="organizations_administered")


class CreatorPlan(UUIDModel, TimestampedModel):
    """§31 Creator Marketplace — stub model only, matching blueprint's own framing
    as a future phase ("مرحلة متقدمة بعد تكوين User Base قوي")."""

    creator = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="creator_plans")
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True)
    price_cents = models.PositiveIntegerField()
    creator_revenue_share_percent = models.PositiveSmallIntegerField(default=70)
    is_published = models.BooleanField(default=False)
