# chat/urls.py
"""
REST URL patterns for the chat application.

These are mounted under ``/api/`` by the project-level ``urls.py``,
so the final paths are:

    GET /api/conversations/                                  → InboxListView
    GET /api/conversations/<uuid:conversation_id>/messages/  → MessageHistoryView
"""

from django.urls import path

from .views import InboxListView, MessageHistoryView

app_name = "chat"

urlpatterns = [
    path(
        "conversations/",
        InboxListView.as_view(),
        name="inbox-list",
    ),
    path(
        "conversations/<uuid:conversation_id>/messages/",
        MessageHistoryView.as_view(),
        name="message-history",
    ),
]