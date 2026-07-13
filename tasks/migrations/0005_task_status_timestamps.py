from django.db import migrations, models
from django.db.models import F


def backfill_status_timestamps(apps, schema_editor):
    Task = apps.get_model("tasks", "Task")
    Task.objects.filter(
        status="TO_VERIFY",
        verification_at__isnull=True,
    ).update(verification_at=F("updated_at"))
    Task.objects.filter(status="DONE").update(
        verification_at=F("updated_at"),
        completed_at=F("updated_at"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0004_task_habilitation_request"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="verification_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Mise à vérifier le",
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="completed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Terminée le",
            ),
        ),
        migrations.RunPython(
            backfill_status_timestamps,
            migrations.RunPython.noop,
        ),
    ]
