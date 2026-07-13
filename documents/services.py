from pathlib import Path

from .models import Document, DocumentHistory


def _file_size(file_field, fallback=0):
    if fallback:
        return fallback
    try:
        return file_field.size
    except (FileNotFoundError, OSError, ValueError):
        return 0


def index_source_file(
    *,
    source_module,
    source_type,
    source_id,
    file_field,
    original_filename,
    linked_item_label,
    uploaded_by=None,
    service="",
    created_at=None,
):
    if not file_field:
        return None
    filename = original_filename or Path(file_field.name).name
    lookup = {
        "source_module": source_module,
        "source_type": source_type,
        "source_id": str(source_id),
    }
    document, created = Document.objects.update_or_create(
        **lookup,
        defaults={
            "title": filename,
            "original_filename": filename,
            "file": file_field.name,
            "file_type": Path(filename).suffix.lower().lstrip(".").upper()
            or "FILE",
            "file_size": _file_size(file_field),
            "category": Document.Category.ATTACHMENT,
            "linked_item_label": linked_item_label,
            "uploaded_by": uploaded_by,
            "service": service,
        },
    )
    if created and created_at:
        Document.objects.filter(pk=document.pk).update(created_at=created_at)
        document.created_at = created_at
    if created:
        DocumentHistory.objects.create(
            document=document,
            document_title=document.title,
            user=uploaded_by,
            action=DocumentHistory.Action.CREATED,
            source_module=source_module,
            details=f"Indexe depuis {document.get_source_module_display()}",
        )
    return document


def index_task_attachment(attachment):
    task = attachment.task
    return index_source_file(
        source_module=Document.SourceModule.TASK,
        source_type="tasks.Attachment",
        source_id=attachment.pk,
        file_field=attachment.file,
        original_filename=attachment.original_name,
        linked_item_label=task.title,
        uploaded_by=attachment.uploaded_by,
        service=task.project.name if task.project_id else "",
        created_at=attachment.uploaded_at,
    )


def index_chat_attachment(attachment):
    channel = attachment.message.channel
    return index_source_file(
        source_module=Document.SourceModule.CHAT,
        source_type="chat.ChatMessageAttachment",
        source_id=attachment.pk,
        file_field=attachment.file,
        original_filename=attachment.original_name,
        linked_item_label=channel.name,
        uploaded_by=attachment.uploaded_by,
        service=channel.project.name if channel.project_id else "",
        created_at=attachment.created_at,
    )


def index_legacy_chat_attachment(attachment):
    channel = attachment.message.channel
    return index_source_file(
        source_module=Document.SourceModule.CHAT,
        source_type="projects.TeamMessageAttachment",
        source_id=attachment.pk,
        file_field=attachment.file,
        original_filename=attachment.original_name,
        linked_item_label=channel.name if channel else "Chat equipe",
        uploaded_by=attachment.message.author,
        created_at=attachment.uploaded_at,
    )


def index_habilitation_request(access_request):
    source_type = "access_control.HabilitationRequest"
    if not access_request.attachment:
        Document.objects.filter(
            source_module=Document.SourceModule.HABILITATION_REQUEST,
            source_type=source_type,
            source_id=str(access_request.pk),
        ).delete()
        return None
    return index_source_file(
        source_module=Document.SourceModule.HABILITATION_REQUEST,
        source_type=source_type,
        source_id=access_request.pk,
        file_field=access_request.attachment,
        original_filename=Path(access_request.attachment.name).name,
        linked_item_label=f"{access_request.reference} - {access_request.habilitation.application}",
        uploaded_by=access_request.requester,
        service=access_request.project.name if access_request.project_id else "",
        created_at=access_request.created_at,
    )


def remove_source_document(source_module, source_type, source_id, user=None):
    documents = Document.objects.filter(
        source_module=source_module,
        source_type=source_type,
        source_id=str(source_id),
    )
    for document in documents:
        DocumentHistory.objects.create(
            document=None,
            document_title=document.title,
            user=user,
            action=DocumentHistory.Action.DELETED,
            source_module=document.source_module,
            details="La piece jointe source a ete supprimee.",
        )
    documents.delete()
