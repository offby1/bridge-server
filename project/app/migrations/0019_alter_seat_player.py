# Generated by Django 5.1 on 2024-09-12 20:11

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0018_play_app_play_a_card_can_be_played_only_once'),
    ]

    operations = [
        migrations.AlterField(
            model_name='seat',
            name='player',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='app.player'),
        ),
    ]