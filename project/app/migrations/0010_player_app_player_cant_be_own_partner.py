# Generated by Django 5.1 on 2024-08-22 17:04

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0009_alter_seat_options'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='player',
            constraint=models.CheckConstraint(condition=models.Q(('partner__isnull', True), models.Q(('partner_id', models.F('id')), _negated=True), _connector='OR'), name='app_player_cant_be_own_partner'),
        ),
    ]
