# Generated by Django 5.1.4 on 2025-02-17 16:33

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0069_tournamentsignups"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tournamentsignups",
            name="player",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE, to="app.player"
            ),
        ),
    ]
