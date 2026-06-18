# chat/models.py
import uuid
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL

class Conversation(models.Model):
    TYPE_CHOICES = (
        ("private", "Private"),
        ("group", "Group"),
    )
    
    # Security Upgrade: UUIDs prevent IDOR scraping attacks
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)

    # Only used for group chats
    name = models.CharField(max_length=255, null=True, blank=True)
    image = models.ImageField(upload_to="group_images/", null=True, blank=True)

    # Optimization: instant last message access for the chat list screen
    last_message = models.ForeignKey(
        "Message",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["type"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.type} - {self.id}"


class ConversationParticipant(models.Model):
    ROLE_CHOICES = (
        ("admin", "Admin"),
        ("member", "Member"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="member")
    is_creator = models.BooleanField(default=False)

    # KEY FIELD: Used to calculate unread counts without querying the Message table
    last_read_message = models.ForeignKey(
        "Message",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+"
    )

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "conversation")
        indexes = [
            models.Index(fields=["user", "conversation"]),
        ]

    def __str__(self):
        return f"{self.user} in {self.conversation}"


class Message(models.Model):
    MESSAGE_TYPE = (
        ("text", "Text"),
        ("image", "Image"),
        ("video", "Video"),
        ("file", "File"),
    )
    
    # Security Upgrade: UUIDs prevent IDOR scraping attacks
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages"
    )

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_messages"
    )

    content = models.TextField(null=True, blank=True)

    message_type = models.CharField(
        max_length=10,
        choices=MESSAGE_TYPE,
        default="text"
    )

    file = models.FileField(upload_to="chat_files/", null=True, blank=True)
    
    # --- SCHEDULED MESSAGING INTEGRATION ---
    is_scheduled = models.BooleanField(default=False)
    scheduled_time = models.DateTimeField(null=True, blank=True)
    # Required to cancel or update a scheduled task in Celery
    celery_task_id = models.CharField(max_length=255, null=True, blank=True)
    # ---------------------------------------
    
    # Forwarding
    is_forwarded = models.BooleanField(default=False)
    original_message_id = models.IntegerField(null=True, blank=True)

    # Reply Threading
    reply_to = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replies"
    )

    # Delete for everyone functionality
    is_deleted_for_everyone = models.BooleanField(default=False)
    deleted_for_users = models.ManyToManyField(User, blank=True, related_name="deleted_messages")
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["sender"]),
        ]

    def __str__(self):
        return f"{self.sender} -> {self.conversation}"


class MessageRead(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("message", "user")
        indexes = [
            models.Index(fields=["user", "message"]),
        ]

    def __str__(self):
        return f"Read by {self.user} at {self.seen_at}"


class MessageReaction(models.Model):
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="reactions"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    emoji = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("message", "user")
        indexes = [
            models.Index(fields=["message", "emoji"]),
        ]

    def __str__(self):
        return f"{self.user} reacted {self.emoji} on {self.message_id}"


class UserPresence(models.Model):
    """ Privacy settings governing if others can see when this user is online. """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="presence_settings")
    allow_seen_online = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"Presence settings for {self.user}"


class UserReadReceipt(models.Model):
    """ Privacy settings governing if this user sends read receipts to others. """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="receipt_settings"
    )
    allow_read_receipts = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"Read receipt settings for {self.user}"