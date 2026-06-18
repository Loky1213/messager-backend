# chat/services.py
"""
Service Layer — Single source of truth for all chat-related database operations.

Every method is a plain synchronous function so it can be unit-tested trivially.
Consumers wrap calls with `@database_sync_to_async`; DRF views call them directly.
"""

from django.db import transaction
from django.db.models import Q
from django.contrib.auth import get_user_model

from .models import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageRead,
    UserReadReceipt,
)

User = get_user_model()


class ChatService:
    """Static-method façade over the chat ORM layer."""

    # ------------------------------------------------------------------
    # 1. Conversation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_or_create_private_conversation(user1, user2):
        """
        Return the existing private Conversation between *user1* and *user2*,
        or atomically create one together with both ConversationParticipants.

        Returns:
            tuple[Conversation, bool]  – (conversation, created)
        """
        # Try to find an existing private conversation shared by both users.
        existing = (
            Conversation.objects.filter(type="private")
            .filter(conversationparticipant__user=user1)
            .filter(conversationparticipant__user=user2)
            .distinct()
            .first()
        )

        if existing:
            return existing, False

        # No conversation exists — create one atomically.
        with transaction.atomic():
            conversation = Conversation.objects.create(type="private")

            ConversationParticipant.objects.create(
                user=user1,
                conversation=conversation,
                role="member",
                is_creator=True,
            )
            ConversationParticipant.objects.create(
                user=user2,
                conversation=conversation,
                role="member",
                is_creator=False,
            )

        return conversation, True

    # ------------------------------------------------------------------
    # 2. Messaging
    # ------------------------------------------------------------------

    @staticmethod
    def save_message(
        sender,
        conversation_id,
        content,
        message_type="text",
        is_scheduled=False,
        scheduled_time=None,
        reply_to_id=None,
    ):
        """
        Persist a new Message and, when it is *not* scheduled, denormalize
        `Conversation.last_message` so the inbox list stays fast.

        Args:
            sender:          User instance (the author).
            conversation_id: UUID of the target Conversation.
            content:         Text body of the message.
            message_type:    One of ``text | image | video | file``.
            is_scheduled:    Whether Celery will deliver this later.
            scheduled_time:  Optional datetime for scheduled delivery.
            reply_to_id:     Optional UUID of the parent Message (threading).

        Returns:
            Message instance with ``sender``, ``conversation``, and
            ``reply_to`` already selected/prefetched.
        """
        conversation = Conversation.objects.get(pk=conversation_id)

        # Resolve reply target (if any).
        reply_to = None
        if reply_to_id:
            reply_to = Message.objects.filter(
                pk=reply_to_id,
                conversation=conversation,
            ).first()

        message = Message.objects.create(
            conversation=conversation,
            sender=sender,
            content=content,
            message_type=message_type,
            is_scheduled=is_scheduled,
            scheduled_time=scheduled_time,
            reply_to=reply_to,
        )

        # Denormalize for the inbox screen — skip for scheduled (not yet visible).
        if not is_scheduled:
            conversation.last_message = message
            conversation.save(update_fields=["last_message"])

        # Re-fetch with relations so downstream serialization never N+1s.
        return (
            Message.objects.select_related("sender", "conversation", "reply_to")
            .get(pk=message.pk)
        )

    # ------------------------------------------------------------------
    # 3. Read receipts
    # ------------------------------------------------------------------

    @staticmethod
    def mark_conversation_as_read(user, conversation_id, message_id):
        """
        Record that *user* has read up to *message_id* inside *conversation_id*.

        Side-effects
        ~~~~~~~~~~~~~
        1. ``ConversationParticipant.last_read_message`` is updated.
        2. A ``MessageRead`` row is created (idempotent via get_or_create).
        3. Respects `UserReadReceipt.allow_read_receipts` privacy flag.

        Returns:
            dict — payload suitable for broadcasting over the WebSocket group,
            or ``None`` when read-receipts are disabled by the user's privacy
            settings.
        """
        # Privacy gate — honour the user's read-receipt toggle.
        receipt_settings = UserReadReceipt.objects.filter(user=user).first()
        if receipt_settings and not receipt_settings.allow_read_receipts:
            return None

        # Validate participant membership.
        participant = ConversationParticipant.objects.filter(
            user=user,
            conversation_id=conversation_id,
        ).first()

        if not participant:
            return None

        message = Message.objects.filter(
            pk=message_id,
            conversation_id=conversation_id,
        ).first()

        if not message:
            return None

        # Update the high-water mark on the participant row.
        participant.last_read_message = message
        participant.save(update_fields=["last_read_message"])

        # Persist the fine-grained read record (idempotent).
        MessageRead.objects.get_or_create(message=message, user=user)

        return {
            "type": "read_receipt",
            "conversation_id": str(conversation_id),
            "message_id": str(message_id),
            "user_id": user.pk,
            "username": user.username,
        }

    # ------------------------------------------------------------------
    # 4. WebSocket payload formatting
    # ------------------------------------------------------------------

    @staticmethod
    def format_message_for_websocket(message):
        """
        Return a JSON-safe dictionary suitable for broadcasting over
        Channels.  This is the **single canonical shape** every connected
        client can rely on.

        Args:
            message: A ``Message`` instance (select_related on *sender*
                     and *reply_to* is expected but not required).

        Returns:
            dict
        """
        payload = {
            "type": "chat_message",
            "message": {
                "id": str(message.id),
                "conversation_id": str(message.conversation_id),
                "sender": {
                    "id": message.sender.pk,
                    "username": message.sender.username,
                    "display_name": message.sender.display_name,
                    "profile_picture": message.sender.profile_picture or "",
                },
                "content": message.content,
                "message_type": message.message_type,
                "is_forwarded": message.is_forwarded,
                "is_deleted_for_everyone": message.is_deleted_for_everyone,
                "reply_to": None,
                "created_at": message.created_at.isoformat(),
            },
        }

        # Nest basic reply context when the message is a threaded reply.
        if message.reply_to_id:
            try:
                parent = message.reply_to
                payload["message"]["reply_to"] = {
                    "id": str(parent.id),
                    "sender_username": parent.sender.username if parent.sender else None,
                    "content": (parent.content or "")[:120],  # truncated preview
                }
            except Exception:
                # Defensive — reply_to may have been deleted.
                payload["message"]["reply_to"] = None

        return payload
