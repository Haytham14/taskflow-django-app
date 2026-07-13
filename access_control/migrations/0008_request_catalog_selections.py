from django.db import migrations, models
import django.db.models.deletion


ACCESS_TYPE_LABELS = {
    "READ": "Lecture",
    "WRITE": "Ecriture",
    "ADMIN": "Administration",
    "TEMPORARY": "Temporaire",
}


def migrate_request_selections(apps, schema_editor):
    HabilitationItem = apps.get_model("access_control", "HabilitationItem")
    HabilitationAccessType = apps.get_model(
        "access_control", "HabilitationAccessType"
    )
    HabilitationRequest = apps.get_model(
        "access_control", "HabilitationRequest"
    )

    for access_request in HabilitationRequest.objects.select_related(
        "habilitation"
    ):
        application = access_request.habilitation
        item = HabilitationItem.objects.filter(application=application).first()
        if item is None:
            item = HabilitationItem.objects.create(
                application=application,
                name=application.application,
            )
        access_request.requested_habilitations.add(item)

        type_name = ACCESS_TYPE_LABELS.get(
            access_request.access_type,
            access_request.access_type,
        )
        access_type = HabilitationAccessType.objects.filter(
            application=application,
            name__iexact=type_name,
        ).first()
        if access_type is None:
            access_type = HabilitationAccessType.objects.create(
                application=application,
                name=type_name,
                position=application.access_types.count(),
            )
        access_request.requested_access_type = access_type
        access_request.save(update_fields=["requested_access_type"])


def restore_legacy_access_type(apps, schema_editor):
    HabilitationRequest = apps.get_model(
        "access_control", "HabilitationRequest"
    )
    reverse_labels = {label: value for value, label in ACCESS_TYPE_LABELS.items()}
    for access_request in HabilitationRequest.objects.select_related(
        "requested_access_type"
    ):
        type_name = (
            access_request.requested_access_type.name
            if access_request.requested_access_type
            else "Lecture"
        )
        access_request.access_type = reverse_labels.get(type_name, "READ")
        access_request.save(update_fields=["access_type"])


class Migration(migrations.Migration):

    dependencies = [
        ("access_control", "0007_remove_habilitation_access_type_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="habilitationrequest",
            name="requested_access_type",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="requests",
                to="access_control.habilitationaccesstype",
            ),
        ),
        migrations.AddField(
            model_name="habilitationrequest",
            name="requested_habilitations",
            field=models.ManyToManyField(
                related_name="requests",
                to="access_control.habilitationitem",
            ),
        ),
        migrations.RunPython(
            migrate_request_selections,
            restore_legacy_access_type,
        ),
        migrations.AlterField(
            model_name="habilitationrequest",
            name="requested_access_type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="requests",
                to="access_control.habilitationaccesstype",
            ),
        ),
        migrations.RemoveField(
            model_name="habilitationrequest",
            name="access_type",
        ),
    ]
