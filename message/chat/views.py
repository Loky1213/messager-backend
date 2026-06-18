# chat/views.py
"""
DRF views serving historical chat data over standard HTTP.

These endpoints are called once when a chat screen opens so the client
can render past messages and the inbox list before the WebSocket
begins streaming live updates.
"""

from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import CursorPagination
from django.db.models import F

from .models import (
    Conversation,
    ConversationParticipant,
    Message,
)
from .serializers import ConversationSerializer, MessageSerializer


# ------------------------------------------------------------------
# Pagination
# ------------------------------------------------------------------


class MessageCursorPagination(CursorPagination):
    """
    Cursor-based pagination for message history.

    Cursor pagination is ideal here because:
    1. It is O(1) regardless of offset depth (no ``OFFSET N`` scan).
    2. It handles real-time inserts gracefully — no skipped / duplicated rows.
    """

    page_size = 30
    ordering = "-created_at"
    cursor_query_param = "cursor"


# ------------------------------------------------------------------
# Views
# ------------------------------------------------------------------


class InboxListView(generics.ListAPIView):
    """
    ``GET /api/conversations/``

    Returns every Conversation the authenticated user participates in,
    ordered by the most recent message (``last_message__created_at DESC``).

    The response includes a nested ``last_message`` object so the
    frontend can render the inbox preview line without a second request.
    """

    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Conversation.objects.filter(
                conversationparticipant__user=self.request.user,
            )
            .select_related(
                "last_message",
                "last_message__sender",
                "last_message__reply_to",
            )
            .order_by(
                F("last_message__created_at").desc(nulls_last=True)
            )
        )


class MessageHistoryView(generics.ListAPIView):
    """
    ``GET /api/conversations/<uuid:conversation_id>/messages/``

    Returns cursor-paginated messages for a specific conversation.

    **Object-level permission**: only users who are participants of
    the conversation may access this endpoint.
    """

    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = MessageCursorPagination

    def get_queryset(self):
        conversation_id = self.kwargs["conversation_id"]

        # Object-level permission check — raise 403 early.
        is_participant = ConversationParticipant.objects.filter(
            user=self.request.user,
            conversation_id=conversation_id,
        ).exists()

        if not is_participant:
            raise PermissionDenied(
                "You are not a participant of this conversation."
            )

        return (
            Message.objects.filter(
                conversation_id=conversation_id,
                is_scheduled=False,
            )
            .exclude(deleted_for_users=self.request.user)
            .select_related("sender", "reply_to", "reply_to__sender")
            .order_by("-created_at")
        )
