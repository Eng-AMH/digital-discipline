from django.urls import path

from apps.social import views

urlpatterns = [
    path("friends/", views.FriendRequestListCreateView.as_view(), name="friend-list-create"),
    path("friends/<uuid:request_id>/decide/", views.FriendRequestDecideView.as_view(), name="friend-decide"),

    path("accountability/", views.AccountabilityLinkListCreateView.as_view(), name="accountability-list-create"),
    path("accountability/<uuid:link_id>/confirm/", views.AccountabilityLinkConfirmView.as_view(), name="accountability-confirm"),

    path("challenges/", views.ChallengeListCreateView.as_view(), name="challenge-list-create"),
    path("challenges/<uuid:challenge_id>/join/", views.ChallengeJoinView.as_view(), name="challenge-join"),
    path("challenges/<uuid:challenge_id>/members/", views.ChallengeMembersView.as_view(), name="challenge-members"),

    path("league/", views.FocusLeagueView.as_view(), name="focus-league"),

    path("family/", views.FamilyGroupListCreateView.as_view(), name="family-list-create"),
    path("family/<uuid:family_group_id>/members/", views.FamilyMemberListCreateView.as_view(), name="family-member-list-create"),
    path("family/<uuid:family_group_id>/members/<uuid:member_id>/role/", views.FamilyMemberRoleChangeView.as_view(), name="family-member-role-change"),
]
