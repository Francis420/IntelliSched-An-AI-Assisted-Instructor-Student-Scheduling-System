from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/scheduler/(?P<batch_id>[^/]+)/$", consumers.SchedulerProgressConsumer.as_asgi()),
]
