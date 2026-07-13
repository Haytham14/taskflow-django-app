from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def request_attachment_upload_path(instance, filename):
    return f"habilitation_requests/{instance.reference or 'draft'}/{filename}"


class Habilitation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    application = models.CharField(max_length=180, unique=True)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responsible_habilitations",
    )
    procedure = models.TextField(blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["application"]

    def __str__(self):
        return self.application


class HabilitationItem(models.Model):
    application = models.ForeignKey(
        Habilitation, on_delete=models.CASCADE, related_name="items"
    )
    name = models.CharField(max_length=180)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=("application", "name"),
                name="unique_habilitation_name_per_application",
            )
        ]

    def __str__(self):
        return self.name


class HabilitationAccessType(models.Model):
    application = models.ForeignKey(
        Habilitation, on_delete=models.CASCADE, related_name="access_types"
    )
    name = models.CharField(max_length=120)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=("application", "name"),
                name="unique_access_type_per_application",
            )
        ]

    def __str__(self):
        return self.name


class HabilitationRequest(models.Model):
    class Urgency(models.TextChoices):
        LOW = "LOW", "Faible"
        MEDIUM = "MEDIUM", "Moyenne"
        HIGH = "HIGH", "Elevee"
        CRITICAL = "CRITICAL", "Critique"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        SUBMITTED = "SUBMITTED", "Soumise"
        PENDING_MANAGER = "PENDING_MANAGER", "En attente manager"
        PENDING_BUSINESS = "PENDING_BUSINESS", "En attente responsable metier"
        PENDING_ADMIN = "PENDING_ADMIN", "En attente administrateur"
        INFO_REQUESTED = "INFO_REQUESTED", "En attente d'information"
        GRANTED = "GRANTED", "Accordee"
        REJECTED = "REJECTED", "Refusee"
        EXPIRED = "EXPIRED", "Expiree"
        REVOKED = "REVOKED", "Revoquee"

    reference = models.CharField(max_length=30, unique=True, blank=True)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="habilitation_requests",
    )
    habilitation = models.ForeignKey(
        Habilitation, on_delete=models.PROTECT, related_name="requests"
    )
    requested_habilitations = models.ManyToManyField(
        HabilitationItem,
        related_name="requests",
    )
    requested_access_type = models.ForeignKey(
        HabilitationAccessType,
        on_delete=models.PROTECT,
        related_name="requests",
    )
    urgency = models.CharField(
        max_length=20,
        choices=Urgency.choices,
        default=Urgency.MEDIUM,
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="habilitation_requests",
    )
    justification = models.TextField()
    requested_start_date = models.DateField()
    requested_duration_days = models.PositiveIntegerField(null=True, blank=True)
    requested_end_date = models.DateField(null=True, blank=True)
    attachment = models.FileField(upload_to=request_attachment_upload_path, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    current_step = models.CharField(max_length=80, default="Brouillon")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference or f"Demande #{self.pk}"

    def save(self, *args, **kwargs):
        if not self.reference:
            year = timezone.localdate().year
            next_number = HabilitationRequest.objects.count() + 1
            self.reference = f"HAB-{year}-{next_number:04d}"
        if self.requested_start_date and self.requested_end_date:
            self.requested_duration_days = (
                self.requested_end_date - self.requested_start_date
            ).days
        else:
            self.requested_duration_days = None
        super().save(*args, **kwargs)

    @property
    def department(self):
        return "Non renseigne"

    @property
    def manager_name(self):
        return "Responsable hierarchique"

    def get_access_type_display(self):
        return self.requested_access_type.name


class HabilitationRequestStep(models.Model):
    class Status(models.TextChoices):
        WAITING = "WAITING", "A venir"
        PENDING = "PENDING", "En attente"
        APPROVED = "APPROVED", "Approuvee"
        REJECTED = "REJECTED", "Refusee"
        INFO_REQUESTED = "INFO_REQUESTED", "Information demandee"
        SKIPPED = "SKIPPED", "Ignoree"

    class Decision(models.TextChoices):
        NONE = "NONE", "-"
        APPROVE = "APPROVE", "Approuver"
        REJECT = "REJECT", "Refuser"
        REQUEST_INFO = "REQUEST_INFO", "Demander information"
        GRANT = "GRANT", "Attribuer"

    request = models.ForeignKey(
        HabilitationRequest, on_delete=models.CASCADE, related_name="steps"
    )
    step_name = models.CharField(max_length=100)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="habilitation_steps",
    )
    decision = models.CharField(max_length=20, choices=Decision.choices, default=Decision.NONE)
    comment = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    validated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.request.reference} - {self.step_name}"


class HabilitationAssignment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        EXPIRES_SOON = "EXPIRES_SOON", "Expire bientot"
        EXPIRED = "EXPIRED", "Expiree"
        REVOKED = "REVOKED", "Revoquee"
        SUSPENDED = "SUSPENDED", "Suspendue"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="habilitation_assignments"
    )
    habilitation = models.ForeignKey(
        Habilitation, on_delete=models.PROTECT, related_name="assignments"
    )
    request = models.ForeignKey(
        HabilitationRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments",
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_habilitations",
    )
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revoked_habilitations",
    )
    revoked_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["end_date"]

    def __str__(self):
        return f"{self.user} - {self.habilitation}"

    @property
    def matricule(self):
        return f"U{self.user_id:04d}" if self.user_id else "-"

    @property
    def expires_soon(self):
        if self.status != self.Status.ACTIVE:
            return False
        if not self.end_date:
            return False
        today = timezone.localdate()
        return today <= self.end_date <= today + timedelta(days=30)


class EmployeeMovement(models.Model):
    class MovementType(models.TextChoices):
        ARRIVAL = "ARRIVAL", "Arrivee d'un salarie"
        INTERNAL_MOVE = "INTERNAL_MOVE", "Mutation interne"
        ROLE_CHANGE = "ROLE_CHANGE", "Changement de fonction"
        DEPARTURE = "DEPARTURE", "Depart"
        SUSPENSION = "SUSPENSION", "Suspension temporaire"

    class Status(models.TextChoices):
        PENDING = "PENDING", "A traiter"
        IN_PROGRESS = "IN_PROGRESS", "En cours"
        DONE = "DONE", "Traite"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employee_movements"
    )
    movement_type = models.CharField(max_length=30, choices=MovementType.choices)
    old_department = models.CharField(max_length=120, blank=True)
    new_department = models.CharField(max_length=120, blank=True)
    old_position = models.CharField(max_length=120, blank=True)
    new_position = models.CharField(max_length=120, blank=True)
    effective_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    justification = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-effective_date", "-created_at"]

    def __str__(self):
        return f"{self.user} - {self.get_movement_type_display()}"


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_audit_logs",
    )
    action = models.CharField(max_length=80)
    entity_type = models.CharField(max_length=80)
    entity_id = models.CharField(max_length=80, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} - {self.action}"
