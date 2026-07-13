from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Project(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Actif"
        COMPLETED = "COMPLETED", "Terminé"

    name = models.CharField(max_length=200, verbose_name="Nom")
    description = models.TextField(blank=True, verbose_name="Description")
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="Statut",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Terminé le",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="projects",
        verbose_name="Membres",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_projects",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.status == self.Status.COMPLETED and self.completed_at is None:
            self.completed_at = timezone.now()
        elif self.status == self.Status.ACTIVE and self.completed_at is not None:
            self.completed_at = None

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"completed_at"}
        super().save(*args, **kwargs)

    def can_access(self, user):
        return user.is_admin_role or self.members.filter(pk=user.pk).exists()


class TeamChannel(models.Model):
    name = models.CharField(max_length=80, unique=True, verbose_name="Nom")
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    description = models.CharField(max_length=180, blank=True, verbose_name="Description")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_channels",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"#{self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name) or "channel"
        super().save(*args, **kwargs)


class TeamMessage(models.Model):
    channel = models.ForeignKey(
        TeamChannel,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="messages",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="team_messages",
    )
    body = models.TextField(verbose_name="Message")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Message de {self.author}"


def chat_attachment_upload_path(instance, filename):
    return f"team_chat_attachments/{instance.message_id}/{filename}"


class TeamMessageAttachment(models.Model):
    message = models.ForeignKey(TeamMessage, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=chat_attachment_upload_path, verbose_name="Fichier")
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return self.original_name or self.file.name

    def extension(self):
        name = self.original_name or self.file.name
        return Path(name).suffix.lower().lstrip(".")

    def file_type_label(self):
        extension = self.extension()
        labels = {
            "pdf": "PDF",
            "doc": "Word",
            "docx": "Word",
            "xls": "Excel",
            "xlsx": "Excel",
            "csv": "CSV",
            "txt": "Texte",
            "sql": "SQL",
            "jpg": "Image",
            "jpeg": "Image",
            "png": "Image",
        }
        return labels.get(extension, extension.upper() if extension else "Fichier")

    def filesize_display(self):
        try:
            size = self.file.size
        except (FileNotFoundError, ValueError, OSError):
            return ""
        size = float(size)
        for unit in ("o", "Ko", "Mo", "Go"):
            if size < 1024:
                return f"{size:.0f} {unit}" if unit == "o" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} To"
