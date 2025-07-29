import json
from channels.generic.websocket import AsyncWebsocketConsumer
from aimatching.models import MatchingProgress
from django.core.serializers.json import DjangoJSONEncoder
from asgiref.sync import sync_to_async

class ProgressConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.batch_id = self.scope['url_route']['kwargs']['batch_id']
        self.group_name = f"progress_{self.batch_id}"

        # Join room group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def progress_update(self, event):
        await self.send(text_data=json.dumps(event["data"], cls=DjangoJSONEncoder))