# chat/serializers.py
"""
DRF serializers for the chat application.

These are used exclusively by the REST views that serve *historical* data
(inbox list, message history).  Real-time payloads go through
``ChatService.format_message_for_websocket`` instead.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import (
    Conversation,
    ConversationParticipant,
    Message,
)

User = get_user_model()


# ------------------------------------------------------------------
# Lightweight nested serializers
# ------------------------------------------------------------------


class SenderSerializer(serializers.ModelSerializer):
    """Minimal user representation embedded inside messages."""

    class Meta:
        model = User
        fields = ("id", "username", "display_name", "profile_picture")
        read_only_fields = fields


class ReplyToSerializer(serializers.ModelSerializer):
    """
    Compact representation of the parent message in a reply thread.
    Only the bare minimum needed for the reply preview bubble.
    """

    sender_username = serializers.CharField(
        source="sender.username", read_only=True
    )

    class Meta:
        model = Message
        fields = ("id", "sender_username", "content", "message_type")
        read_only_fields = fields


# ------------------------------------------------------------------
# Main serializers
# ------------------------------------------------------------------


class MessageSerializer(serializers.ModelSerializer):
    """
    Full representation of a ``Message`` for REST responses.

    * ``sender`` is expanded to ``SenderSerializer``.
    * ``reply_to`` is expanded to ``ReplyToSerializer`` when present.
    """

    sender = SenderSerializer(read_only=True)
    reply_to = ReplyToSerializer(read_only=True)

    class Meta:
        model = Message
        fields = (
            "id",
            "conversation",
            "sender",
            "content",
            "message_type",
            "file",
            "is_scheduled",
            "scheduled_time",
            "is_forwarded",
            "reply_to",
            "is_deleted_for_everyone",
            "created_at",
        )
        read_only_fields = fields


class ConversationSerializer(serializers.ModelSerializer):
    """
    Serializer powering the inbox/chat-list screen.

    Includes:
    * ``last_message`` nested via ``MessageSerializer`` for the preview line.
    * ``participants`` — list of users in the conversation.
    * ``unread_count`` — injected by the view via annotation or
      calculated from the requesting user's ``last_read_message``.
    """

    last_message = MessageSerializer(read_only=True)
    participants = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            "id",
            "type",
            "name",
            "image",
            "last_message",
            "participants",
            "unread_count",
            "created_at",
        )
        read_only_fields = fields

    # -- helpers -------------------------------------------------------

    def get_participants(self, obj):
        """
        Return a list of participants with their basic profile info.
        Uses prefetched data when available.
        """
        qs = ConversationParticipant.objects.filter(
            conversation=obj
        ).select_related("user")

        return [
            {
                "id": cp.user.pk,
                "username": cp.user.username,
                "display_name": cp.user.display_name,
                "profile_picture": cp.user.profile_picture or "",
                "role": cp.role,
            }
            for cp in qs
        ]

    def get_unread_count(self, obj):
        """
        Calculate how many messages are unread for the requesting user.

        Logic:
            If ``last_read_message`` is set → count messages created after it.
            Otherwise → every message in the conversation is unread.
        """
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return 0

        participant = ConversationParticipant.objects.filter(
            conversation=obj,
            user=request.user,
        ).first()

        if not participant:
            return 0

        messages_qs = Message.objects.filter(
            conversation=obj,
            is_scheduled=False,
        ).exclude(sender=request.user)

        if participant.last_read_message_id:
            # Count messages newer than the last one the user read.
            messages_qs = messages_qs.filter(
                created_at__gt=participant.last_read_message.created_at,
            )

        return messages_qs.count()
