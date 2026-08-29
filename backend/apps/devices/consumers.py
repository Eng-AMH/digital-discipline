"""
Live Device Health status — §9's "Last heartbeat: 15 sec ago" and "⚠ Protection
Interrupted" banner, pushed in real time rather than polled. This is one of the two
deliberately-scoped uses of Channels per architecture doc §12 ("kept, narrowed" —
not force-fit everywhere).

Server-side push happens from apps.devices.services.record_heartbeat and
record_tamper_event via channel_layer.group_send — see services.py.
"""
import json

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class DeviceHealthConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if self.user is None or self.user.is_anonymous:
            await self.close(code=4001)
            return
        # One group per user (not per device) — the web dashboard shows ALL of a
        # user's devices' health at once (§9/§48 Multi-Device), so a single
        # subscription per logged-in user is the right granularity, not one
        # socket per device.
        self.group_name = f"device_health_user_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def device_health_update(self, event):
        """Handler name must match the `type` key sent via group_send in services.py."""
        await self.send_json(event["payload"])
