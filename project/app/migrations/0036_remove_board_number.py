# Generated by Django 5.1.2 on 2024-11-17 21:58

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0035_alter_board_number_alter_board_tournament'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='board',
            name='number',
        ),
    ]
