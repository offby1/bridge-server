# Generated by Django 5.1.2 on 2024-11-06 15:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0031_auto_20241106_1511'),
    ]

    operations = [
        migrations.AlterField(
            model_name='board',
            name='number',
            field=models.SmallIntegerField(unique=True),
        ),
    ]