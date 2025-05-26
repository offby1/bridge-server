import logging

import pytest

from django.contrib import auth
from django.http import HttpResponseForbidden

from app.models import Board, Hand, Player, Tournament
from app.views.hand import (
    _error_response_or_viewfunc,
    _everything_read_only_view,
    _interactive_view,
)
from app.testutils import play_out_hand

logger = logging.getLogger()


@pytest.fixture
def two_hands(db, everybodys_password) -> None:
    t1 = Tournament.objects.create()
    b1, _ = Board.objects.get_or_create_from_display_number(
        display_number=1, tournament=t1, group="A"
    )

    North, South, East, West = [
        Player.objects.create(
            user=auth.models.User.objects.create(username=name, password=everybodys_password),
        )
        for name in ["North", "East", "South", "West"]
    ]

    North.partner_with(South)
    East.partner_with(West)

    Ding, Dong, Witch, Dead = [
        Player.objects.create(
            user=auth.models.User.objects.create(username=name, password=everybodys_password),
        )
        for name in ["Ding", "Dong", "Witch", "Dead"]
    ]

    Ding.partner_with(Dong)
    Witch.partner_with(Dead)

    h1 = Hand.objects.create(
        board=b1, North=North, East=East, West=West, South=South, table_display_number=1
    )

    play_out_hand(h1)

    Hand.objects.create(
        board=b1, North=Ding, East=Dong, West=Witch, South=Dead, table_display_number=2
    )


expectation_matrix = {
    "North": {
        "b1t1": _everything_read_only_view,
        "b1t2": _everything_read_only_view,
        "b2t1": _interactive_view,
    },
    "Ding": {
        "b1t1": HttpResponseForbidden,
        "b1t2": _interactive_view,
        "b2t1": HttpResponseForbidden,
    },
}


def test_dispatcher(two_hands):
    assert Hand.objects.filter(board__display_number=1).count() == 2

    for h in Hand.objects.all():
        logger.info("hand %s: %s", h, [p.name for p in h.players()])

    for player_name, by_board_and_table_display_numbers in expectation_matrix.items():
        player = Player.objects.get_by_name(player_name)
        for unpack_me, expected in by_board_and_table_display_numbers.items():
            board_display_number, table_display_number = int(unpack_me[1]), int(unpack_me[3])

            hand = Hand.objects.get(
                board__display_number=board_display_number,
                table_display_number=table_display_number,
            )
            actual = _error_response_or_viewfunc(hand, player.user)
            if isinstance(actual, HttpResponseForbidden):
                assert type(actual) is expected
            else:
                assert actual == expected
