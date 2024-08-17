# Generated by Django 5.1 on 2024-08-16 23:34

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0006_remove_playermessage_from_player_and_more'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='Lobby',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'db_table_comment': 'Serves no purpose other than acting as a target for lobby messages',
            },
        ),
        migrations.RemoveField(
            model_name='message',
            name='player_recipient',
        ),
        migrations.RemoveField(
            model_name='message',
            name='table_recipient',
        ),
        migrations.AddField(
            model_name='message',
            name='recipient_content_type',
            field=models.ForeignKey(default=None, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='message',
            name='recipient_object_id',
            field=models.PositiveIntegerField(default=None),
            preserve_default=False,
        ),
        migrations.AddIndex(
            model_name='message',
            index=models.Index(fields=['recipient_content_type', 'recipient_object_id'], name='app_message_recipie_1391da_idx'),
        ),
    ]