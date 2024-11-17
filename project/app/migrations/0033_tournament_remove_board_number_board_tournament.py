# Generated by Django 5.1.2 on 2024-11-17 23:07

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0032_alter_board_number'),
    ]

    operations = [
        migrations.CreateModel(
            name='Tournament',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
        ),
        migrations.RemoveField(
            model_name='board',
            name='number',
        ),
        migrations.AddField(
            model_name='board',
            name='tournament',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='app.tournament'),
        ),
    ]
