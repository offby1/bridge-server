# Generated by Django 5.1.4 on 2025-01-24 00:31

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0055_auto_20250123_2237"),
    ]

    operations = [
        migrations.AlterField(
            model_name="table",
            name="tournament",
            field=models.ForeignKey(
                default=None,
                on_delete=django.db.models.deletion.CASCADE,
                to="app.tournament",
            ),
            preserve_default=False,
        ),
    ]
