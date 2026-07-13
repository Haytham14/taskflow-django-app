from django.contrib import admin

from .models import (
    ChatChannel,
    ChatChannelMember,
    ChatChannelTask,
    ChatMention,
    ChatMessage,
    ChatMessageAttachment,
    ChatMessageReaction,
    ChatMessageReadReceipt,
    ChatUserPresence,
)


class ChatChannelMemberInline(admin.TabularInline):
    model = ChatChannelMember
    extra = 0
    autocomplete_fields = ["user"]


@admin.register(ChatUserPresence)
class ChatUserPresenceAdmin(admin.ModelAdmin):
    list_display = ("user", "is_available", "last_seen_at", "updated_at")
    list_filter = ("is_available",)
    search_fields = ("user__name", "user__email")
    autocomplete_fields = ("user",)


@admin.register(ChatChannel)
class ChatChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "channel_type", "project", "task", "is_archived", "created_by", "created_at")
    list_filter = ("channel_type", "is_archived", "created_at")
    search_fields = ("name", "description", "slug")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["project", "task", "created_by"]
    inlines = [ChatChannelMemberInline]


@admin.register(ChatChannelMember)
class ChatChannelMemberAdmin(admin.ModelAdmin):
    list_display = ("channel", "user", "role", "is_muted", "joined_at", "last_seen_at")
    list_filter = ("role", "is_muted", "joined_at")
    search_fields = ("channel__name", "user__name", "user__email")
    autocomplete_fields = ["channel", "user"]


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "channel", "sender", "message_type", "is_edited", "is_deleted", "created_at")
    list_filter = ("message_type", "is_edited", "is_deleted", "created_at")
    search_fields = ("content", "channel__name", "sender__name", "sender__email")
    autocomplete_fields = ["channel", "sender", "parent_message"]


@admin.register(ChatMessageAttachment)
class ChatMessageAttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "message", "file_type", "file_size", "uploaded_by", "created_at")
    list_filter = ("file_type", "created_at")
    search_fields = ("original_name", "message__content", "uploaded_by__name")
    autocomplete_fields = ["message", "uploaded_by"]


@admin.register(ChatMessageReaction)
class ChatMessageReactionAdmin(admin.ModelAdmin):
    list_display = ("emoji", "message", "user", "created_at")
    list_filter = ("emoji", "created_at")
    search_fields = ("emoji", "message__content", "user__name")
    autocomplete_fields = ["message", "user"]


@admin.register(ChatMessageReadReceipt)
class ChatMessageReadReceiptAdmin(admin.ModelAdmin):
    list_display = ("message", "user", "read_at")
    list_filter = ("read_at",)
    search_fields = ("message__content", "user__name", "user__email")
    autocomplete_fields = ["message", "user"]


@admin.register(ChatMention)
class ChatMentionAdmin(admin.ModelAdmin):
    list_display = ("message", "mentioned_user", "created_at")
    list_filter = ("created_at",)
    search_fields = ("message__content", "mentioned_user__name", "mentioned_user__email")
    autocomplete_fields = ["message", "mentioned_user"]


@admin.register(ChatChannelTask)
class ChatChannelTaskAdmin(admin.ModelAdmin):
    list_display = ("channel", "task", "created_by", "created_at")
    list_filter = ("created_at",)
    search_fields = ("channel__name", "task__title", "created_by__name")
    autocomplete_fields = ["channel", "task", "created_by"]
