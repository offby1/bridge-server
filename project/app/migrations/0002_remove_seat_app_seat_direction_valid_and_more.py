# Generated by Django 5.0.7 on 2024-08-06 15:06

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0001_initial'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='seat',
            name='app_seat_direction_valid',
        ),
        migrations.RemoveField(
            model_name='player',
            name='looking_for_partner',
        ),
        migrations.AddField(
            model_name='player',
            name='partner',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='app.player'),
        ),
        migrations.AlterField(
            model_name='seat',
            name='direction',
            field=models.SmallIntegerField(choices=[(1, 'NORTH'), (2, 'EAST'), (3, 'SOUTH'), (4, 'WEST')]),
        ),
        migrations.AddConstraint(
            model_name='seat',
            constraint=models.CheckConstraint(check=models.Q(('direction__in', {1: 'NORTH', 2: 'EAST', 3: 'SOUTH', 4: 'WEST'})), name='app_seat_direction_valid'),
        ),
    ]