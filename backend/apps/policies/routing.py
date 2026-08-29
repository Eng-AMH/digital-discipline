from django.urls import re_path

from apps.policies.consumers import FocusSessionConsumer

websocket_urlpatterns = [
    re_path(r"ws/focus-session/$", FocusSessionConsumer.as_asgi()),
]
