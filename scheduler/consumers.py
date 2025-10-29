import json
from channels.generic.websocket import AsyncWebsocketConsumer
from scheduler.models import SchedulerProgress
from django.core.serializers.json import DjangoJSONEncoder
from asgiref.sync import sync_to_async

class SchedulerProgressConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.batch_id = self.scope['url_route']['kwargs']['batch_id']
        self.group_name = f"scheduler_{self.batch_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send current state on connect
        progress = await sync_to_async(SchedulerProgress.objects.filter)(batch_id=self.batch_id)
        progress_obj = await sync_to_async(lambda: progress.first())()
        if progress_obj:
            await self.send(text_data=json.dumps({
                "status": progress_obj.status,
                "message": progress_obj.message,
                "progress": progress_obj.progress,
            }, cls=DjangoJSONEncoder))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def progress_update(self, event):
        await self.send(text_data=json.dumps(event["data"], cls=DjangoJSONEncoder))
