from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("presence/", views.presence, name="presence"),
    path("unread-count/", views.unread_count, name="unread_count"),
    path("channels/", views.channels, name="channels"),
    path("direct-conversations/", views.direct_conversation, name="direct_conversation"),
    path("channels/<int:channel_id>/", views.channel_detail, name="channel_detail"),
    path("channels/<int:channel_id>/members/", views.channel_members, name="channel_members"),
    path(
        "channels/<int:channel_id>/members/<int:user_id>/",
        views.channel_member_detail,
        name="channel_member_detail",
    ),
    path("channels/<int:channel_id>/messages/", views.channel_messages, name="channel_messages"),
    path("channels/<int:channel_id>/mark-read/", views.mark_channel_read, name="mark_channel_read"),
    path("channels/<int:channel_id>/linked-tasks/", views.linked_tasks, name="linked_tasks"),
    path("channels/<int:channel_id>/shared-files/", views.shared_files, name="shared_files"),
    path("attachments/<int:attachment_id>/download/", views.attachment_download, name="attachment_download"),
    path("messages/<int:message_id>/", views.message_detail, name="message_detail"),
    path("messages/<int:message_id>/reactions/", views.message_reactions, name="message_reactions"),
]
