from django.contrib import admin

from .models import Attachment, Comment, Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "status", "priority", "deadline", "assigned_to", "created_by", "created_at")
    list_filter = ("project", "status", "priority", "deadline")
    search_fields = ("title", "description")
    autocomplete_fields = ("project", "assigned_to", "assignees", "created_by")
    date_hierarchy = "created_at"


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("task", "author", "created_at")
    search_fields = ("body",)
    autocomplete_fields = ("task", "author")
    date_hierarchy = "created_at"


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("task", "original_name", "uploaded_by", "uploaded_at")
    search_fields = ("original_name",)
    autocomplete_fields = ("task", "uploaded_by")
    date_hierarchy = "uploaded_at"
