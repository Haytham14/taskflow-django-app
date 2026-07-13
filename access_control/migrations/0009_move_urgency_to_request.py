from django.db import migrations, models


def copy_urgency_to_requests(apps, schema_editor):
    HabilitationRequest = apps.get_model(
        "access_control", "HabilitationRequest"
    )
    for access_request in HabilitationRequest.objects.select_related(
        "habilitation"
    ):
        access_request.urgency = access_request.habilitation.criticality
        access_request.save(update_fields=["urgency"])


def restore_catalog_urgency(apps, schema_editor):
    Habilitation = apps.get_model("access_control", "Habilitation")
    for application in Habilitation.objects.all():
        first_request = application.requests.order_by("created_at").first()
        application.criticality = (
            first_request.urgency if first_request else "MEDIUM"
        )
        application.save(update_fields=["criticality"])


class Migration(migrations.Migration):

    dependencies = [
        ("access_control", "0008_request_catalog_selections"),
    ]

    operations = [
        migrations.AddField(
            model_name="habilitationrequest",
            name="urgency",
            field=models.CharField(
                choices=[
                    ("LOW", "Faible"),
                    ("MEDIUM", "Moyenne"),
                    ("HIGH", "Elevee"),
                    ("CRITICAL", "Critique"),
                ],
                default="MEDIUM",
                max_length=20,
            ),
        ),
        migrations.RunPython(
            copy_urgency_to_requests,
            restore_catalog_urgency,
        ),
        migrations.RemoveField(
            model_name="habilitation",
            name="criticality",
        ),
    ]
