# chat/admin.py
from django.contrib import admin
from .models import (
    Conversation, 
    ConversationParticipant, 
    Message, 
    MessageRead, 
    MessageReaction
)

class ConversationParticipantInline(admin.TabularInline):
    model = ConversationParticipant
    extra = 1

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    # This makes sure you can easily see and copy the UUID!
    list_display = ('id', 'type', 'created_at')
    readonly_fields = ('id',)
    inlines = [ConversationParticipantInline]

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'conversation', 'message_type', 'created_at')
    readonly_fields = ('id',)

# Register the rest with standard views
admin.site.register(ConversationParticipant)
admin.site.register(MessageRead)
admin.site.register(MessageReaction)