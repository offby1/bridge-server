# Generated by Django 5.1.4 on 2025-01-18 23:50

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0047_rename_boards_played_player_boards_played_v2"),
    ]

    operations = [
        migrations.RenameField(
            model_name="player",
            old_name="boards_played_v2",
            new_name="boards_played",
        ),
    ]
