from django.urls import path

from apps.notifications import views

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="notification-list"),
    path("<uuid:notification_id>/read/", views.NotificationMarkReadView.as_view(), name="notification-mark-read"),
    path("mark-all-read/", views.NotificationMarkAllReadView.as_view(), name="notification-mark-all-read"),
    path("preferences/", views.NotificationPreferenceListView.as_view(), name="notification-preferences"),
    path("preferences/update/", views.NotificationPreferenceUpdateView.as_view(), name="notification-preference-update"),
]
