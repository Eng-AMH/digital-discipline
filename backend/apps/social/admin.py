from django.contrib import admin

from apps.social.models import (
    FriendRequest, AccountabilityLink, Challenge, ChallengeMember, League, FamilyGroup, FamilyMember,
)


@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ["from_user", "to_user", "status", "created_at"]
    list_filter = ["status"]


@admin.register(AccountabilityLink)
class AccountabilityLinkAdmin(admin.ModelAdmin):
    list_display = ["user", "partner", "status", "created_at"]
    list_filter = ["status"]


class ChallengeMemberInline(admin.TabularInline):
    model = ChallengeMember
    extra = 0


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ["title", "created_by", "status", "start_date", "duration_days", "token_reward"]
    list_filter = ["status"]
    inlines = [ChallengeMemberInline]


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ["scope", "organization_key", "week_number", "year"]
    list_filter = ["scope", "year"]


class FamilyMemberInline(admin.TabularInline):
    model = FamilyMember
    extra = 0


@admin.register(FamilyGroup)
class FamilyGroupAdmin(admin.ModelAdmin):
    list_display = ["name", "created_by", "created_at"]
    inlines = [FamilyMemberInline]


@admin.register(FamilyMember)
class FamilyMemberAdmin(admin.ModelAdmin):
    list_display = ["family_group", "user", "role", "detailed_activity_visible_to_guardians"]
    list_filter = ["role"]
