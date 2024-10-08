# Generated by Django 5.0.7 on 2024-08-06 05:00

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Table",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Player",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("looking_for_partner", models.BooleanField(default=False)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
                    ),
                ),
            ],
            options={
                "ordering": ["user__username"],
            },
        ),
        migrations.CreateModel(
            name="Seat",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "direction",
                    models.CharField(
                        choices=[("N", "North"), ("E", "East"), ("S", "South"), ("W", "West")],
                        max_length=1,
                    ),
                ),
                (
                    "player",
                    models.OneToOneField(
                        null=True, on_delete=django.db.models.deletion.CASCADE, to="app.player"
                    ),
                ),
                (
                    "table",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="app.table"),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Call",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "serialized",
                    models.CharField(
                        db_comment="A short string with which we can create a bridge.contract.Call object",
                        max_length=10,
                    ),
                ),
                (
                    "seat",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="app.seat"),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="seat",
            constraint=models.UniqueConstraint(
                fields=("player", "table"), name="no_more_than_one_player_per_table"
            ),
        ),
        migrations.AddConstraint(
            model_name="seat",
            constraint=models.UniqueConstraint(
                fields=("direction", "table"), name="no_more_than_four_directions_per_table"
            ),
        ),
        migrations.AddConstraint(
            model_name="seat",
            constraint=models.CheckConstraint(
                condition=models.Q(("direction__in", ["N", "E", "S", "W"])),
                name="app_seat_direction_valid",
            ),
        ),
    ]
