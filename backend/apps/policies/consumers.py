"""
Live Focus Session countdown — §7 Focus Mode's timer needs to feel real-time on the
dashboard (and stay in sync if the user has the web dashboard open on a second
device while the session runs on their phone), which is the second deliberately-
scoped Channels use case per architecture doc §12.
"""
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class FocusSessionConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if self.user is None or self.user.is_anonymous:
            await self.close(code=4001)
            return
        self.group_name = f"focus_session_user_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def focus_session_update(self, event):
        await self.send_json(event["payload"])
