from django.db import migrations, models
import django.db.models.deletion


DEFAULT_APPLICATIONS = {
    "SAP001": {
        "application": "SAP",
        "access_type": "READ_WRITE",
        "items": [
            "Acces SAP Achat",
            "Acces SAP Finance",
            "Acces SAP Consultation",
        ],
    },
    "ORA002": {
        "application": "Oracle",
        "access_type": "ADMINISTRATION",
        "items": [
            "Acces Oracle Production",
            "Acces Oracle Lecture seule",
            "Acces Oracle Administration",
        ],
    },
    "NET003": {
        "application": "VPN Entreprise",
        "access_type": "REMOTE",
        "items": [
            "Acces VPN standard",
            "Acces VPN temporaire",
        ],
    },
}


def migrate_catalog_forward(apps, schema_editor):
    Habilitation = apps.get_model("access_control", "Habilitation")
    HabilitationItem = apps.get_model("access_control", "HabilitationItem")
    type_mapping = {
        "APPLICATION": "READ_WRITE",
        "DATABASE": "ADMINISTRATION",
        "NETWORK": "REMOTE",
        "PHYSICAL": "PHYSICAL",
        "EQUIPMENT": "READ",
        "INTERNAL_SYSTEM": "READ_WRITE",
    }
    used_applications = set()

    for item in Habilitation.objects.order_by("id"):
        defaults = DEFAULT_APPLICATIONS.get(item.code)
        base_application = defaults["application"] if defaults else item.name
        application = base_application
        suffix = 2
        while application.casefold() in used_applications:
            application = f"{base_application} ({suffix})"
            suffix += 1
        used_applications.add(application.casefold())

        item.application = application
        item.access_type = (
            defaults["access_type"]
            if defaults
            else type_mapping.get(item.type, "READ")
        )
        item.save(update_fields=["application", "access_type"])

        names = defaults["items"] if defaults else [item.name]
        for position, name in enumerate(names):
            HabilitationItem.objects.create(
                application=item,
                name=name,
                position=position,
            )


def migrate_catalog_backward(apps, schema_editor):
    Habilitation = apps.get_model("access_control", "Habilitation")
    type_mapping = {
        "ADMINISTRATION": "DATABASE",
        "REMOTE": "NETWORK",
        "PHYSICAL": "PHYSICAL",
    }

    for item in Habilitation.objects.prefetch_related("items").order_by("id"):
        first_item = item.items.order_by("position", "id").first()
        item.code = f"APP{item.pk:04d}"
        item.name = first_item.name if first_item else item.application
        item.type = type_mapping.get(item.access_type, "APPLICATION")
        item.save(update_fields=["code", "name", "type"])


class Migration(migrations.Migration):

    dependencies = [
        ("access_control", "0003_optional_request_end_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="habilitation",
            name="access_type",
            field=models.CharField(
                choices=[
                    ("READ", "Lecture"),
                    ("WRITE", "Ecriture"),
                    ("READ_WRITE", "Lecture / ecriture"),
                    ("ADMINISTRATION", "Administration"),
                    ("REMOTE", "Distant"),
                    ("TEMPORARY", "Temporaire"),
                    ("PHYSICAL", "Physique"),
                ],
                default="READ",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="habilitation",
            name="application",
            field=models.CharField(blank=True, max_length=180, null=True),
        ),
        migrations.CreateModel(
            name="HabilitationItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=180)),
                ("position", models.PositiveIntegerField(default=0)),
                (
                    "application",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="access_control.habilitation",
                    ),
                ),
            ],
            options={
                "ordering": ["position", "id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("application", "name"),
                        name="unique_habilitation_name_per_application",
                    )
                ],
            },
        ),
        migrations.RunPython(migrate_catalog_forward, migrate_catalog_backward),
        migrations.AlterField(
            model_name="habilitation",
            name="application",
            field=models.CharField(max_length=180, unique=True),
        ),
        migrations.RemoveField(
            model_name="habilitation",
            name="code",
        ),
        migrations.RemoveField(
            model_name="habilitation",
            name="name",
        ),
        migrations.RemoveField(
            model_name="habilitation",
            name="type",
        ),
        migrations.AlterModelOptions(
            name="habilitation",
            options={"ordering": ["application"]},
        ),
    ]
