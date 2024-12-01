# Generated by Django 5.1.2 on 2024-11-17 22:23

from app.models.board import BOARDS_PER_TOURNAMENT
from django.db import migrations


def backfill_tournaments(apps, schema_editor) -> None:
    Board = apps.get_model("app", "Board")
    Tournament = apps.get_model("app", "Tournament")

    for index, board in enumerate(Board.objects.order_by("id").all()):
        needed_number_of_tournaments = 1 + (index // BOARDS_PER_TOURNAMENT)
        if Tournament.objects.count() < needed_number_of_tournaments:
            # Rather than create a tournament with a specific primary key, we allow django and postgres to choose a
            # default primary key.  This avoids the surprising behavior documented at
            # https://code.djangoproject.com/ticket/35916
            t = Tournament.objects.create()
        else:
            t = Tournament.objects.order_by("-id").first()

        board.tournament = t
        board.save()


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0033_tournament_remove_board_number_board_tournament"),
    ]

    operations = [
        migrations.operations.RunPython(code=backfill_tournaments),
    ]