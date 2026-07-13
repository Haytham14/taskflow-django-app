from django.contrib import admin

from .models import Document, DocumentHistory


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "source_module",
        "file_type",
        "status",
        "uploaded_by",
        "created_at",
    )
    list_filter = ("category", "source_module", "status")
    search_fields = ("title", "original_filename", "linked_item_label")
    autocomplete_fields = ("uploaded_by",)


@admin.register(DocumentHistory)
class DocumentHistoryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "document_title", "user")
    list_filter = ("action", "source_module")
    search_fields = ("document_title", "details")
