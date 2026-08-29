"""
Notification views. §41 Privacy Center explicitly lists notification settings as
user-controllable — NotificationPreferenceListView/UpdateView is that control,
using the opt-out model documented on NotificationPreference (absence of a row =
enabled by default).
"""
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.models import Notification, NotificationPreference, NotificationType
from apps.notifications.serializers import NotificationSerializer, NotificationPreferenceSerializer


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class NotificationMarkReadView(APIView):
    def post(self, request, notification_id):
        notification = get_object_or_404(Notification, id=notification_id, user=request.user)
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)


class NotificationMarkAllReadView(APIView):
    def post(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"marked_read": count})


class NotificationPreferenceListView(APIView):
    """
    Returns the effective preference for EVERY notification type (not just ones
    with an explicit row) — this is what makes the opt-out model usable from a
    client: the UI can render a toggle for every type without special-casing
    "no row yet means default on."
    """

    def get(self, request):
        explicit_prefs = {
            p.notification_type: p.is_enabled
            for p in NotificationPreference.objects.filter(user=request.user)
        }
        result = [
            {"notification_type": choice_value, "is_enabled": explicit_prefs.get(choice_value, True)}
            for choice_value, _ in NotificationType.choices
        ]
        return Response(result)


class NotificationPreferenceUpdateView(APIView):
    def post(self, request):
        notification_type = request.data.get("notification_type")
        is_enabled = request.data.get("is_enabled")
        if notification_type not in dict(NotificationType.choices) or is_enabled is None:
            return Response({"detail": "notification_type and is_enabled are required."}, status=400)

        pref, _ = NotificationPreference.objects.update_or_create(
            user=request.user, notification_type=notification_type, defaults={"is_enabled": is_enabled}
        )
        return Response(NotificationPreferenceSerializer(pref).data)
