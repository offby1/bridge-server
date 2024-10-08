# Generated by Django 5.1 on 2024-08-26 17:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0011_board'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='board',
            name='cards',
        ),
        migrations.AddField(
            model_name='board',
            name='east_cards',
            field=models.CharField(default=None, max_length=26),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='board',
            name='north_cards',
            field=models.CharField(default=None, max_length=26),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='board',
            name='south_cards',
            field=models.CharField(default=None, max_length=26),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='board',
            name='west_cards',
            field=models.CharField(default=None, max_length=26),
            preserve_default=False,
        ),
    ]
