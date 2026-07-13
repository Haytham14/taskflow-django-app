from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.auth.models import Permission
from django.db import models


class UserManager(BaseUserManager):
    """Manager for the custom, email-based User model."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", User.Role.MEMBER)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class AppRole(models.Model):
    name = models.CharField(max_length=120, unique=True, verbose_name="Nom du rôle")
    description = models.TextField(blank=True, verbose_name="Description")
    permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name="taskflow_roles",
        verbose_name="Permissions",
    )
    system_key = models.CharField(max_length=30, unique=True, null=True, blank=True)
    is_system = models.BooleanField(default=False, verbose_name="Rôle système")
    permissions_initialized = models.BooleanField(default=False, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Rôle"
        verbose_name_plural = "Rôles"

    def __str__(self):
        return self.name


class Department(models.Model):
    name = models.CharField(max_length=120, unique=True, verbose_name="Nom du service")
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    description = models.TextField(blank=True, verbose_name="Périmètre / description")
    manager = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_departments",
        verbose_name="Responsable",
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Service / département"
        verbose_name_plural = "Services / départements"

    def __str__(self):
        return f"{self.code} · {self.name}"


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model matching the required schema:
    ID, Name, Email, Password, Role.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrateur"
        MEMBER = "MEMBER", "Membre"
        COLLABORATOR = "COLLABORATOR", "Collaborateur"
        MANAGER = "MANAGER", "Responsable hierarchique"
        BUSINESS_OWNER = "BUSINESS_OWNER", "Responsable metier"
        ACCESS_ADMIN = "ACCESS_ADMIN", "Administrateur habilitations"
        HR = "HR", "RH"
        AUDITOR = "AUDITOR", "Auditeur"
        SYSTEM_ADMIN = "SYSTEM_ADMIN", "Administrateur systeme"

    name = models.CharField(max_length=150, verbose_name="Nom")
    email = models.EmailField(unique=True, verbose_name="E-mail")
    role = models.CharField(
        max_length=30, choices=Role.choices, default=Role.MEMBER, verbose_name="Rôle"
    )
    custom_role = models.ForeignKey(
        AppRole,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        verbose_name="Rôle et permissions",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
        verbose_name="Service / département",
    )

    is_active = models.BooleanField(default=True, verbose_name="Actif")
    is_staff = models.BooleanField(
        default=False, help_text="Donne accès au site d'administration Django intégré."
    )
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name or self.email

    def get_full_name(self):
        return self.name

    def get_short_name(self):
        return self.name

    @property
    def is_admin_role(self):
        return self.role in (self.Role.ADMIN, self.Role.SYSTEM_ADMIN)

    @property
    def is_access_admin_role(self):
        return self.role in (self.Role.ADMIN, self.Role.SYSTEM_ADMIN, self.Role.ACCESS_ADMIN)

    def get_role_display(self):
        if self.custom_role_id:
            return self.custom_role.name
        return dict(self.Role.choices).get(self.role, self.role)

    def get_all_permissions(self, obj=None):
        permissions = set(super().get_all_permissions(obj))
        if obj is None and self.is_active and self.custom_role_id:
            permissions.update(
                f"{app_label}.{codename}"
                for app_label, codename in self.custom_role.permissions.values_list(
                    "content_type__app_label", "codename"
                )
            )
        return permissions

    def has_perm(self, perm, obj=None):
        return bool(self.is_active and (self.is_superuser or perm in self.get_all_permissions(obj)))
