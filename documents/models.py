from pathlib import Path

from django.conf import settings
from django.db import models
from django.urls import reverse


def document_upload_path(instance, filename):
    return f"documents/manual/{filename}"


class Document(models.Model):
    class Category(models.TextChoices):
        REPORT = "REPORT", "Rapport"
        PROCEDURE = "PROCEDURE", "Procedure"
        TEMPLATE = "TEMPLATE", "Modele"
        FORM = "FORM", "Formulaire"
        CHECKLIST = "CHECKLIST", "Checklist"
        ATTACHMENT = "ATTACHMENT", "Piece jointe"
        OTHER = "OTHER", "Autre"

    class SourceModule(models.TextChoices):
        MANUAL = "manual", "Ajout manuel"
        TASK = "task", "Tache"
        PROJECT = "project", "Projet"
        CHAT = "chat", "Chat equipe"
        HABILITATION_REQUEST = (
            "habilitation_request",
            "Demande d'habilitation",
        )
        VALIDATION = "validation", "Validation"
        HR_MOVEMENT = "hr_movement", "Mouvement RH"
        USER = "user", "Utilisateur"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Actif"
        ARCHIVED = "ARCHIVED", "Archive"

    title = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    file = models.FileField(upload_to=document_upload_path)
    file_type = models.CharField(max_length=40, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    category = models.CharField(
        max_length=30,
        choices=Category.choices,
        default=Category.OTHER,
    )
    source_module = models.CharField(
        max_length=40,
        choices=SourceModule.choices,
        default=SourceModule.MANUAL,
    )
    source_type = models.CharField(max_length=120, blank=True)
    source_id = models.CharField(max_length=80, blank=True)
    linked_item_label = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    service = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["source_module", "source_type", "source_id"]),
            models.Index(fields=["category", "is_archived"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.file:
            filename = self.original_filename or Path(self.file.name).name
            self.original_filename = filename
            self.file_type = (
                Path(filename).suffix.lower().lstrip(".").upper() or "FILE"
            )
            if not self.title:
                self.title = filename
            if not self.file_size:
                try:
                    self.file_size = self.file.size
                except (FileNotFoundError, OSError, ValueError):
                    self.file_size = 0
        self.is_archived = self.status == self.Status.ARCHIVED
        super().save(*args, **kwargs)

    @property
    def source_url(self):
        if self.source_module == self.SourceModule.TASK and self.source_id:
            return reverse("tasks:task_detail", args=[self.source_id])
        if (
            self.source_module == self.SourceModule.HABILITATION_REQUEST
            and self.source_id
        ):
            return reverse("access_control:request_detail", args=[self.source_id])
        if self.source_module == self.SourceModule.PROJECT and self.source_id:
            return reverse("projects:project_board", args=[self.source_id])
        if self.source_module == self.SourceModule.CHAT:
            return reverse("work_chat")
        return ""

    @property
    def file_size_display(self):
        size = float(self.file_size or 0)
        for unit in ("o", "Ko", "Mo", "Go"):
            if size < 1024:
                return f"{size:.0f} {unit}" if unit == "o" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} To"


class DocumentHistory(models.Model):
    class Action(models.TextChoices):
        CREATED = "CREATED", "Ajout document"
        DOWNLOADED = "DOWNLOADED", "Telechargement"
        OPENED = "OPENED", "Ouverture"
        UPDATED = "UPDATED", "Modification"
        ARCHIVED = "ARCHIVED", "Archivage"
        RESTORED = "RESTORED", "Restauration"
        DELETED = "DELETED", "Suppression"

    document = models.ForeignKey(
        Document,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="history",
    )
    document_title = models.CharField(max_length=255)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_history",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    source_module = models.CharField(
        max_length=40,
        choices=Document.SourceModule.choices,
        blank=True,
    )
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()} - {self.document_title}"
