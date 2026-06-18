# chat/middleware.py
"""
Custom JWT authentication middleware for Django Channels WebSocket connections.

Usage (in asgi.py):
    from chat.middleware import TokenAuthMiddleware
    TokenAuthMiddleware(URLRouter(chat.routing.websocket_urlpatterns))

The middleware intercepts the ASGI ``scope`` *before* the consumer is
instantiated.  It reads the JWT access token from the query-string
parameter ``token`` (e.g. ``ws://host/ws/chat/<id>/?token=eyJ...``),
validates it via Simple JWT, and attaches the corresponding ``User``
to ``scope["user"]``.

If the token is absent or invalid the scope user is set to
``AnonymousUser`` so the consumer can reject the connection cleanly.
"""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError

User = get_user_model()


@database_sync_to_async
def get_user_from_token(token_string):
    """
    Validate a raw JWT string and return the matching ``User``.

    Returns ``AnonymousUser`` when the token is expired, tampered with,
    or the referenced user no longer exists / is inactive.
    """
    try:
        validated_token = AccessToken(token_string)
        user_id = validated_token["user_id"]
        user = User.objects.get(pk=user_id)
        if not user.is_active:
            return AnonymousUser()
        return user
    except (TokenError, User.DoesNotExist, KeyError):
        return AnonymousUser()


class TokenAuthMiddleware(BaseMiddleware):
    """
    ASGI middleware that authenticates WebSocket connections using a
    Simple JWT access token passed as a query-string parameter.

    Compatible with Django Channels 4+.
    """

    async def __call__(self, scope, receive, send):
        # Parse the raw query string from the ASGI scope.
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = parse_qs(query_string)

        token_list = query_params.get("token", [])
        token = token_list[0] if token_list else None

        if token:
            scope["user"] = await get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)
