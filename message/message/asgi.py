import os
import sys
import asyncio

# --- THE WINDOWS ASYNC BUG FIX ---
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# ---------------------------------

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'message.settings')

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

# Import AFTER django_asgi_app is initialized (models must be ready).
import chat.routing
from chat.middleware import TokenAuthMiddleware

application = ProtocolTypeRouter({
    # 1. Standard HTTP requests are routed to normal Django views
    "http": django_asgi_app,

    # 2. WebSocket requests are authenticated via JWT and routed to consumers
    "websocket": AllowedHostsOriginValidator(
        TokenAuthMiddleware(
            URLRouter(
                chat.routing.websocket_urlpatterns
            )
        )
    ),
})