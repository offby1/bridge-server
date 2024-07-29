# Generated by Django 5.0.1 on 2024-07-29 19:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bs_app', '0002_player_name_alter_player_table'),
    ]

    operations = [
        migrations.AlterField(
            model_name='club',
            name='name',
            field=models.CharField(max_length=100, unique=True),
        ),
        migrations.AlterField(
            model_name='player',
            name='name',
            field=models.CharField(max_length=50, unique=True),
        ),
        migrations.AddConstraint(
            model_name='table',
            constraint=models.UniqueConstraint(fields=('name', 'club'), name='composite_primary_key'),
        ),
    ]
