# Generated by Django 5.1 on 2024-09-08 19:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0017_player_is_human'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='play',
            constraint=models.UniqueConstraint(fields=('hand', 'serialized'), name='app_play_a_card_can_be_played_only_once'),
        ),
    ]
