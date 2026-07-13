from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from access_control.models import HabilitationRequest
from chat.models import ChatMessageAttachment
from projects.models import TeamMessageAttachment
from tasks.models import Attachment

from .models import Document
from .services import (
    index_chat_attachment,
    index_habilitation_request,
    index_legacy_chat_attachment,
    index_task_attachment,
    remove_source_document,
)


@receiver(post_save, sender=Attachment)
def index_task_file(sender, instance, **kwargs):
    index_task_attachment(instance)


@receiver(post_save, sender=ChatMessageAttachment)
def index_chat_file(sender, instance, **kwargs):
    index_chat_attachment(instance)


@receiver(post_save, sender=TeamMessageAttachment)
def index_legacy_chat_file(sender, instance, **kwargs):
    index_legacy_chat_attachment(instance)


@receiver(post_save, sender=HabilitationRequest)
def index_request_file(sender, instance, **kwargs):
    index_habilitation_request(instance)


@receiver(post_delete, sender=Attachment)
def remove_task_file(sender, instance, **kwargs):
    remove_source_document(
        Document.SourceModule.TASK,
        "tasks.Attachment",
        instance.pk,
        instance.uploaded_by,
    )


@receiver(post_delete, sender=ChatMessageAttachment)
def remove_chat_file(sender, instance, **kwargs):
    remove_source_document(
        Document.SourceModule.CHAT,
        "chat.ChatMessageAttachment",
        instance.pk,
        instance.uploaded_by,
    )


@receiver(post_delete, sender=TeamMessageAttachment)
def remove_legacy_chat_file(sender, instance, **kwargs):
    remove_source_document(
        Document.SourceModule.CHAT,
        "projects.TeamMessageAttachment",
        instance.pk,
        instance.message.author,
    )


@receiver(post_delete, sender=HabilitationRequest)
def remove_request_file(sender, instance, **kwargs):
    remove_source_document(
        Document.SourceModule.HABILITATION_REQUEST,
        "access_control.HabilitationRequest",
        instance.pk,
        instance.requester,
    )
