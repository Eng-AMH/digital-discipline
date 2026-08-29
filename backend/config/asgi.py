"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# get_asgi_application() must be called before importing anything that touches
# Django models (Channels routing imports consumers, which import models) — this
# ordering is required by Django's app-registry startup, not a style choice.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.auth import AuthMiddlewareStack  # noqa: E402
from apps.devices.routing import websocket_urlpatterns as device_ws_patterns  # noqa: E402
from apps.policies.routing import websocket_urlpatterns as focus_ws_patterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter(device_ws_patterns + focus_ws_patterns)
        ),
    }
)
