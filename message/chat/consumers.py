# chat/consumers.py
"""
Async WebSocket consumer for real-time chat.

Responsibilities
~~~~~~~~~~~~~~~~
- Accept only authenticated users who are participants of the conversation.
- Route incoming JSON payloads by their ``type`` key:
    • ``chat_message``  – persist via ChatService, broadcast to the group.
    • ``typing``        – broadcast a typing indicator (no DB write).
    • ``read_receipt``  – persist via ChatService, broadcast to the group.
- Define the matching server→client handler for each event type.
"""

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import ConversationParticipant
from .services import ChatService

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    """Full-duplex WebSocket endpoint for a single Conversation room."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self):
        """
        Accept the connection only when the user is authenticated *and*
        is a participant of the requested conversation.
        """
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.room_group_name = f"chat_{self.room_id}"
        self.user = self.scope.get("user")

        # Gate 1 — authentication
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        # Gate 2 — conversation membership
        is_participant = await self._is_participant()
        if not is_participant:
            await self.close(code=4003)
            return

        # Join the Channels Redis group for this room.
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )
        await self.accept()

    async def disconnect(self, close_code):
        """Leave the Redis group on disconnect."""
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name,
        )

    # ------------------------------------------------------------------
    # Inbound (client → server)
    # ------------------------------------------------------------------

    async def receive(self, text_data):
        """
        Parse incoming JSON and route by the ``type`` key.

        Expected client payloads::

            # Send a message
            {"type": "chat_message", "content": "Hello!", "message_type": "text"}
            {"type": "chat_message", "content": "Reply!", "message_type": "text", "reply_to": "<uuid>"}

            # Typing indicator
            {"type": "typing"}

            # Read receipt
            {"type": "read_receipt", "message_id": "<uuid>"}
        """
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                "error": "Invalid JSON payload.",
            }))
            return

        msg_type = data.get("type")

        if msg_type == "chat_message":
            await self._handle_chat_message(data)
        elif msg_type == "typing":
            await self._handle_typing()
        elif msg_type == "read_receipt":
            await self._handle_read_receipt(data)
        else:
            await self.send(text_data=json.dumps({
                "error": f"Unknown message type: '{msg_type}'.",
            }))

    # ------------------------------------------------------------------
    # Inbound handlers
    # ------------------------------------------------------------------

    async def _handle_chat_message(self, data):
        """Persist the message and broadcast to the room group."""
        content = data.get("content", "").strip()
        message_type = data.get("message_type", "text")
        reply_to_id = data.get("reply_to")

        if not content:
            await self.send(text_data=json.dumps({
                "error": "Message content cannot be empty.",
            }))
            return

        # Persist (runs in a thread via database_sync_to_async).
        message = await self._save_message(
            content=content,
            message_type=message_type,
            reply_to_id=reply_to_id,
        )

        # Format for broadcast.
        payload = await self._format_message(message)

        # Broadcast to every connection in the group.
        await self.channel_layer.group_send(
            self.room_group_name,
            payload,
        )

    async def _handle_typing(self):
        """Broadcast a typing indicator — no database write."""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "typing",
                "user_id": self.user.pk,
                "username": self.user.username,
            },
        )

    async def _handle_read_receipt(self, data):
        """Persist the read receipt and broadcast the update."""
        message_id = data.get("message_id")
        if not message_id:
            await self.send(text_data=json.dumps({
                "error": "message_id is required for read_receipt.",
            }))
            return

        result = await self._mark_as_read(message_id)

        if result:
            await self.channel_layer.group_send(
                self.room_group_name,
                result,  # already has type="read_receipt"
            )

    # ------------------------------------------------------------------
    # Outbound (server → client)  —  Channels dispatch by event["type"]
    # ------------------------------------------------------------------

    async def chat_message(self, event):
        """Send the chat message payload to the WebSocket client."""
        await self.send(text_data=json.dumps(event))

    async def typing(self, event):
        """Send a typing indicator to the WebSocket client."""
        # Don't echo the indicator back to the sender.
        if event.get("user_id") == self.user.pk:
            return

        await self.send(text_data=json.dumps({
            "type": "typing",
            "user_id": event["user_id"],
            "username": event["username"],
        }))

    async def read_receipt(self, event):
        """Send a read-receipt update to the WebSocket client."""
        await self.send(text_data=json.dumps({
            "type": "read_receipt",
            "conversation_id": event["conversation_id"],
            "message_id": event["message_id"],
            "user_id": event["user_id"],
            "username": event["username"],
        }))

    # ------------------------------------------------------------------
    # Async ↔ sync bridges (database_sync_to_async wrappers)
    # ------------------------------------------------------------------

    @database_sync_to_async
    def _is_participant(self):
        """Check whether self.user belongs to the conversation."""
        return ConversationParticipant.objects.filter(
            user=self.user,
            conversation_id=self.room_id,
        ).exists()

    @database_sync_to_async
    def _save_message(self, content, message_type, reply_to_id=None):
        return ChatService.save_message(
            sender=self.user,
            conversation_id=self.room_id,
            content=content,
            message_type=message_type,
            reply_to_id=reply_to_id,
        )

    @database_sync_to_async
    def _format_message(self, message):
        return ChatService.format_message_for_websocket(message)

    @database_sync_to_async
    def _mark_as_read(self, message_id):
        return ChatService.mark_conversation_as_read(
            user=self.user,
            conversation_id=self.room_id,
            message_id=message_id,
        )
