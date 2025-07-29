import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Intellisched.settings")

# Make sure Django is fully loaded
django.setup()

import aimatching.routing  # <-- import AFTER django.setup()

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            aimatching.routing.websocket_urlpatterns
        )
    ),
})
