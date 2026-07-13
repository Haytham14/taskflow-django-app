from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

MAX_ATTACHMENT_SIZE_MB = 10

ALLOWED_ATTACHMENT_EXTENSIONS = [
    # Images
    "jpg", "jpeg", "png",
    # Documents
    "pdf", "doc", "docx", "xls", "xlsx", "txt",
    # Data
    "csv", "sql",
]


def validate_attachment_size(value):
    limit_bytes = MAX_ATTACHMENT_SIZE_MB * 1024 * 1024
    if value.size > limit_bytes:
        raise ValidationError(f"Le fichier doit faire {MAX_ATTACHMENT_SIZE_MB} Mo maximum.")


validate_attachment_extension = FileExtensionValidator(
    allowed_extensions=ALLOWED_ATTACHMENT_EXTENSIONS,
    message="Ce type de fichier n'est pas autorisé. Types autorisés : JPG, JPEG, PNG, PDF, DOC/DOCX, XLS/XLSX, TXT, CSV, SQL.",
)


def attachment_upload_path(instance, filename):
    return f"task_attachments/{instance.task_id}/{filename}"


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "TODO", "À faire"
        IN_PROGRESS = "IN_PROGRESS", "En cours"
        TO_VERIFY = "TO_VERIFY", "À vérifier"
        DONE = "DONE", "Terminé"

    class Priority(models.TextChoices):
        LOW = "LOW", "Faible"
        MEDIUM = "MEDIUM", "Moyenne"
        HIGH = "HIGH", "Élevée"
        CRITICAL = "CRITICAL", "Critique"

    # Statuses a regular member can no longer change once a task reaches
    # them — only an admin can move a task out of these from here on.
    LOCKED_FOR_MEMBERS = (Status.TO_VERIFY, Status.DONE)

    title = models.CharField(max_length=200, verbose_name="Titre")
    description = models.TextField(blank=True, verbose_name="Description")
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.TODO, verbose_name="Statut"
    )
    priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.MEDIUM, verbose_name="Priorité"
    )

    deadline = models.DateTimeField(null=True, blank=True, verbose_name="Delai")

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
        verbose_name="Projet",
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
        verbose_name="Assigné à",
    )
    assignees = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="assigned_tasks",
        verbose_name="Utilisateurs assignés",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_tasks",
        verbose_name="Créé par",
    )

    habilitation_request = models.ForeignKey(
        "access_control.HabilitationRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
        verbose_name="Demande d'habilitation",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verification_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Mise à vérifier le",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Terminée le",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        previous_status = None
        if self.pk:
            previous_status = (
                type(self).objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )

        changed_fields = []
        now = timezone.now()
        if (
            self.status == self.Status.TO_VERIFY
            and previous_status != self.Status.TO_VERIFY
            and self.verification_at is None
        ):
            self.verification_at = now
            changed_fields.append("verification_at")
        if (
            self.status == self.Status.DONE
            and previous_status != self.Status.DONE
            and self.completed_at is None
        ):
            self.completed_at = now
            changed_fields.append("completed_at")

        update_fields = kwargs.get("update_fields")
        if update_fields is not None and changed_fields:
            kwargs["update_fields"] = set(update_fields) | set(changed_fields)
        super().save(*args, **kwargs)
        # Keep tasks created by legacy/internal workflows visible in the new
        # multi-assignee relation.
        if self.assigned_to_id:
            self.assignees.add(self.assigned_to_id)

    def is_assigned_to(self, user):
        return bool(
            user
            and user.is_authenticated
            and any(assignee.pk == user.pk for assignee in self.assignees.all())
        )

    @property
    def is_locked_for_members(self):
        return self.status in self.LOCKED_FOR_MEMBERS

    @property
    def is_overdue(self):
        return bool(
            self.deadline
            and self.status != self.Status.DONE
            and self.deadline < timezone.now()
        )

    @property
    def deadline_state(self):
        if not self.deadline:
            return "none"
        if self.status == self.Status.DONE:
            return "done"

        remaining = self.deadline - timezone.now()
        if remaining.total_seconds() <= 0:
            return "overdue"
        if remaining.total_seconds() <= 24 * 60 * 60:
            return "soon"
        return "ok"

    @property
    def deadline_remaining_label(self):
        if not self.deadline:
            return "Aucun délai"
        if self.status == self.Status.DONE:
            return "Terminée"

        remaining_seconds = (self.deadline - timezone.now()).total_seconds()
        if remaining_seconds <= 0:
            return "En retard"

        total_minutes = max(1, int((remaining_seconds + 59) // 60))
        days = total_minutes // (24 * 60)
        hours = (total_minutes % (24 * 60)) // 60
        minutes = total_minutes % 60

        if days:
            if hours:
                return f"{days} j {hours} h restantes"
            return f"{days} j restants"
        if hours:
            if minutes:
                return f"{hours} h {minutes} min restantes"
            return f"{hours} h restantes"
        return f"{minutes} min restantes"

    @classmethod
    def priority_rank_annotation(cls):
        """Numeric rank for ordering: Critique, then Élevée, Moyenne, Faible."""
        return Case(
            When(priority=cls.Priority.CRITICAL, then=Value(0)),
            When(priority=cls.Priority.HIGH, then=Value(1)),
            When(priority=cls.Priority.MEDIUM, then=Value(2)),
            When(priority=cls.Priority.LOW, then=Value(3)),
            default=Value(4),
            output_field=IntegerField(),
        )


class Comment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="task_comments",
    )
    body = models.TextField(verbose_name="Commentaire")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Commentaire de {self.author} sur {self.task}"


class Attachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="task_attachments",
    )
    file = models.FileField(
        upload_to=attachment_upload_path,
        validators=[validate_attachment_size, validate_attachment_extension],
        verbose_name="Fichier",
    )
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.original_name or self.file.name

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
