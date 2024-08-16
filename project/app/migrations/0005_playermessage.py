# Generated by Django 5.1 on 2024-08-16 12:33

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0004_lobbymessage'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlayerMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('message', models.TextField(max_length=128)),
                ('from_player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sent_message', to='app.player')),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='received_message', to='app.player')),
            ],
        ),
    ]
