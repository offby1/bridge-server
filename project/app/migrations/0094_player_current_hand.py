# Generated by Django 5.2.1 on 2025-07-05 17:21

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0093_remove_tournament_is_complete_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="player",
            name="current_hand",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE, to="app.hand"
            ),
        ),
    ]
