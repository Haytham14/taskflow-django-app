from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("access_control", "0002_seed_default_habilitations"),
    ]

    operations = [
        migrations.AlterField(
            model_name="habilitationrequest",
            name="requested_duration_days",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="habilitationrequest",
            name="requested_end_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="habilitationassignment",
            name="end_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
