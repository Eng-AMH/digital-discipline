from django.urls import re_path

from apps.devices.consumers import DeviceHealthConsumer

websocket_urlpatterns = [
    re_path(r"ws/device-health/$", DeviceHealthConsumer.as_asgi()),
]
