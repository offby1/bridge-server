# Generated by Django 5.1.2 on 2024-11-18 19:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0032_alter_board_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='player',
            name='currently_seated',
            field=models.BooleanField(default=False),
        ),
    ]
