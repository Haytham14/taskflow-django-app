from django.contrib import admin

from .models import Project, TeamChannel, TeamMessage, TeamMessageAttachment


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "completed_at", "created_by", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "description")
    filter_horizontal = ("members",)
    autocomplete_fields = ("created_by",)
    date_hierarchy = "created_at"


@admin.register(TeamMessage)
class TeamMessageAdmin(admin.ModelAdmin):
    list_display = ("channel", "author", "created_at")
    list_filter = ("channel",)
    search_fields = ("body",)
    autocomplete_fields = ("channel", "author")
    date_hierarchy = "created_at"


@admin.register(TeamChannel)
class TeamChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_by", "created_at")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "description")
    autocomplete_fields = ("created_by",)


@admin.register(TeamMessageAttachment)
class TeamMessageAttachmentAdmin(admin.ModelAdmin):
    list_display = ("message", "original_name", "uploaded_at")
    search_fields = ("original_name",)
    autocomplete_fields = ("message",)
    date_hierarchy = "uploaded_at"
