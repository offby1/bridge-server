# Generated by Django 5.1 on 2024-09-27 19:34

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0023_remove_player_is_human_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='hand',
            name='board',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='app.board'),
        ),
        migrations.AlterField(
            model_name='seat',
            name='player',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='app.player'),
        ),
    ]