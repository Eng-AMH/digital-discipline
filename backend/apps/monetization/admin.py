from django.contrib import admin

from apps.monetization.models import (
    Plan, Subscription, StoreItem, UserInventory, ReferralCode, Referral,
    AmbassadorAccount, CommissionLedgerEntry, Organization, CreatorPlan,
)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["tier", "display_name", "monthly_price_cents", "max_devices", "max_daily_limit_minutes"]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ["user", "plan", "status", "source", "current_period_end"]
    list_filter = ["status", "source", "plan"]
    search_fields = ["user__email", "external_reference_id"]


@admin.register(StoreItem)
class StoreItemAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "token_price", "real_money_price_cents", "requires_plan_tier"]
    list_filter = ["category", "requires_plan_tier"]


@admin.register(UserInventory)
class UserInventoryAdmin(admin.ModelAdmin):
    list_display = ["user", "item", "is_equipped", "acquired_at"]


@admin.register(ReferralCode)
class ReferralCodeAdmin(admin.ModelAdmin):
    list_display = ["user", "code"]
    search_fields = ["code", "user__email"]


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ["referrer", "referred_user", "status", "qualified_at", "reward_granted_days"]
    list_filter = ["status"]
    search_fields = ["referrer__email", "referred_user__email"]


@admin.register(AmbassadorAccount)
class AmbassadorAccountAdmin(admin.ModelAdmin):
    list_display = ["user", "commission_rate_percent", "is_active"]


@admin.register(CommissionLedgerEntry)
class CommissionLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ["ambassador", "amount_cents", "created_at"]

    def has_change_permission(self, request, obj=None):
        return False  # ledger — same rationale as TokenTransaction


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "org_type", "admin_user"]
    list_filter = ["org_type"]


@admin.register(CreatorPlan)
class CreatorPlanAdmin(admin.ModelAdmin):
    list_display = ["title", "creator", "price_cents", "is_published"]
    list_filter = ["is_published"]
