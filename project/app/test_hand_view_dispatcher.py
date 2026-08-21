import logging
import types

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponseForbidden

from app.models import Hand, Player, Tournament
from app.testutils import create_a_tournament, play_out_hand
from app.views.hand import (
    _error_response_or_viewfunc,
    _everything_read_only_view,
    _interactive_view,
)

logger = logging.getLogger()


@pytest.fixture
def setup(db: None) -> Tournament:
    t = create_a_tournament(stage="playing", boards_per_round_per_table=1)

    # play board 1 fully
    b1_hands = Hand.objects.filter(board__display_number=1)
    assert b1_hands.count() == 2
    for h in b1_hands:
        play_out_hand(h)
    # play only one hand of board 2
    b2_hands = Hand.objects.filter(board__display_number=2)
    assert b2_hands.count() == 2
    b2_hands_first = b2_hands.first()
    assert b2_hands_first is not None
    play_out_hand(b2_hands_first)

    assert Hand.objects.count() == 4

    return t


def test_alt(setup: Tournament) -> None:
    import pprint

    pprint.pprint(setup.get_movement())

    all_users = [p.user for p in Player.objects.all()] + [AnonymousUser]

    # Board 1 has been fully played, so everybody can see everything.
    for h in Hand.objects.filter(board__display_number=1):
        for u in all_users:
            assert _error_response_or_viewfunc(h, u) == _everything_read_only_view, f"{u.username}"

    for h in Hand.objects.filter(board__display_number=2):
        # Board 2 has been only partially played.
        for u in all_users:

            def expect(expected):
                __tracebackhide__ = True
                actual = _error_response_or_viewfunc(h, u)

                # TODO -- discriminate on the basis of "callability" -- if it's callable, call it.
                if isinstance(expected, types.FunctionType):
                    if actual != expected:
                        pytest.fail(f"expected {expected=} but got {actual=}")
                else:
                    if actual is not expected and type(actual) is not expected:
                        pytest.fail(f"expected {expected=} but got {type(actual)=}")

            if u.is_anonymous:
                expect(HttpResponseForbidden)
            else:
                match brt := h.board.relationship_to(u.player):
                    case ("AlreadyPlayedIt", _):
                        expect(_everything_read_only_view)
                    case ("CurrentlyPlayingIt", at_hand):
                        expect(_interactive_view if h == at_hand else HttpResponseForbidden)
                    case ("NeverSeenIt", None):
                        expect(HttpResponseForbidden)
                    case _:
                        pytest.fail(f"No idea what {brt=} is")
