import os

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'message.settings')

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

# We will uncomment these lines in the next step once we create the routing file
# import chat.routing 

application = ProtocolTypeRouter({
    # 1. Standard HTTP requests are routed to normal Django views
    "http": django_asgi_app,

    # 2. WebSocket requests will be routed to our Channels consumers
    # "websocket": AllowedHostsOriginValidator(
    #     AuthMiddlewareStack(
    #         URLRouter(
    #             chat.routing.websocket_urlpatterns
    #         )
    #     )
    # ),
})