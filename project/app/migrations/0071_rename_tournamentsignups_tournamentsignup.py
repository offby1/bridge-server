# Generated by Django 5.1.4 on 2025-02-17 19:47

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0070_alter_tournamentsignups_player"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="TournamentSignups",
            new_name="TournamentSignup",
        ),
    ]
