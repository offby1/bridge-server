# Generated by Django 5.1 on 2024-09-24 16:37

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0021_rename_handrecord_handaction'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='HandAction',
            new_name='Hand',
        ),
    ]
