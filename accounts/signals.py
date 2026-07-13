from django.contrib.auth.models import Permission
from django.db.models import Q
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from .models import AppRole


APP_LABELS = ("accounts", "tasks", "projects", "chat", "access_control", "documents")


def permissions_for_system_role(system_key):
    permissions = Permission.objects.filter(content_type__app_label__in=APP_LABELS)
    if system_key in ("ADMIN", "SYSTEM_ADMIN"):
        return permissions
    if system_key == "MEMBER":
        return permissions.filter(
            Q(content_type__app_label="tasks")
            | Q(content_type__app_label="projects", codename__startswith="view_")
            | Q(content_type__app_label="chat")
        )
    if system_key == "COLLABORATOR":
        return permissions.filter(
            Q(content_type__app_label="tasks", codename__startswith="view_")
            | Q(content_type__app_label="projects", codename__startswith="view_")
            | Q(content_type__app_label="chat")
            | Q(content_type__app_label="access_control", content_type__model="habilitationrequest")
            | Q(content_type__app_label="access_control", codename__startswith="view_")
        )
    if system_key in ("MANAGER", "BUSINESS_OWNER"):
        return permissions.filter(
            Q(content_type__app_label="access_control")
            | Q(content_type__app_label="tasks", codename__startswith="view_")
            | Q(content_type__app_label="projects", codename__startswith="view_")
            | Q(content_type__app_label="chat")
        ).exclude(codename__startswith="delete_")
    if system_key == "ACCESS_ADMIN":
        return permissions.filter(content_type__app_label="access_control")
    if system_key == "HR":
        return permissions.filter(
            Q(content_type__app_label="access_control", content_type__model__in=("hrmovement", "auditlog", "habilitationassignment"))
            | Q(content_type__app_label="accounts", codename__startswith="view_")
        )
    if system_key == "AUDITOR":
        return permissions.filter(
            Q(content_type__app_label__in=("access_control", "documents"), codename__startswith="view_")
        )
    return Permission.objects.none()


@receiver(post_migrate, dispatch_uid="accounts.initialize_system_role_permissions")
def initialize_system_role_permissions(**kwargs):
    for role in AppRole.objects.filter(is_system=True, permissions_initialized=False):
        role.permissions.set(permissions_for_system_role(role.system_key))
        role.permissions_initialized = True
        role.save(update_fields=["permissions_initialized"])
