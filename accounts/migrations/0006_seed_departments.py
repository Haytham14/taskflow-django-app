from django.db import migrations


DEPARTMENTS = (
    ("IT", "Direction IT", "Support applicatif, systèmes, sécurité et habilitations."),
    ("RH", "Ressources humaines", "Arrivées, départs, mutations et suspensions."),
    ("METIER", "Responsables métier", "Avis fonctionnels et validations métier."),
    ("PROJ", "Équipes projets", "Production des tâches et demandes opérationnelles."),
    ("AUDIT", "Audit & conformité", "Contrôles, conformité et traçabilité."),
)


def seed_departments(apps, schema_editor):
    Department = apps.get_model("accounts", "Department")
    User = apps.get_model("accounts", "User")
    departments = {}
    for code, name, description in DEPARTMENTS:
        departments[code], _ = Department.objects.get_or_create(
            code=code,
            defaults={"name": name, "description": description, "is_active": True},
        )

    role_to_department = {
        "ADMIN": "IT",
        "SYSTEM_ADMIN": "IT",
        "ACCESS_ADMIN": "IT",
        "HR": "RH",
        "BUSINESS_OWNER": "METIER",
        "AUDITOR": "AUDIT",
        "MEMBER": "PROJ",
        "COLLABORATOR": "PROJ",
        "MANAGER": "PROJ",
    }
    for user in User.objects.filter(department_id=None).iterator():
        department = departments.get(role_to_department.get(user.role))
        if department:
            user.department_id = department.pk
            user.save(update_fields=["department"])

    manager_roles = {
        "IT": ("SYSTEM_ADMIN", "ADMIN", "ACCESS_ADMIN"),
        "RH": ("HR", "ADMIN"),
        "METIER": ("BUSINESS_OWNER", "MANAGER"),
        "PROJ": ("MANAGER", "ADMIN"),
        "AUDIT": ("AUDITOR", "ADMIN"),
    }
    for code, roles in manager_roles.items():
        manager = User.objects.filter(role__in=roles, is_active=True).order_by("name").first()
        if manager:
            departments[code].manager_id = manager.pk
            departments[code].save(update_fields=["manager"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_departments")]
    operations = [migrations.RunPython(seed_departments, migrations.RunPython.noop)]
