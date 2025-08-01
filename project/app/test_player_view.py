from django.contrib import auth

from app.models import Board, Hand, Player, Tournament, TournamentSignup
from app.views.player import _players_for_tournament


def test_player_tournament_filter_thingy(db, rf, everybodys_password) -> None:
    def player_named(name: str) -> Player:
        user, _ = auth.models.User.objects.get_or_create(
            username=name, password=everybodys_password
        )
        some_player, _ = Player.objects.get_or_create(user=user)
        return some_player

    t = Tournament.objects.create()
    players_by_name = {name: player_named(name) for name in ("neither", "signedup", "seated")}

    TournamentSignup.objects.get_or_create(
        defaults=dict(tournament=t), player=players_by_name["signedup"]
    )

    seated = players_by_name["seated"]  # aka North
    south = Player.objects.create_synthetic()
    south.partner_with(seated)

    east = Player.objects.create_synthetic()
    west = Player.objects.create_synthetic()
    east.partner_with(west)

    board, _ = Board.objects.get_or_create_from_display_number(
        display_number=1, tournament=t, group="A"
    )
    # create a hand with that board, and our seated players
    Hand.objects.create(
        board=board, North=seated, East=east, South=south, West=west, table_display_number=1
    )

    players_filter = _players_for_tournament(tournament_display_number=t.display_number)
    players = Player.objects.filter(players_filter)
    player_names = set([p.name for p in players])
    assert "neither" not in player_names
    assert "signedup" in player_names
    assert "seated" in player_names
    assert players.count() == 5
