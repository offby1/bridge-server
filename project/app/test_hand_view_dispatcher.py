import logging
import types

import pytest

from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponseForbidden
from django.utils.timezone import now

from app.models import Hand, Player, Tournament
from app.models.tournament import _do_signup_expired_stuff
from app.views.hand import (
    _error_response_or_viewfunc,
    _everything_read_only_view,
    _interactive_view,
)
from app.testutils import play_out_hand

logger = logging.getLogger()


@pytest.fixture
def setup(db) -> None:
    t = Tournament.objects.create(boards_per_round_per_table=1)
    Player.objects.ensure_eight_players_signed_up(tournament=t)
    t.signup_deadline = now()
    t.save()

    _do_signup_expired_stuff(t)

    # play board 1 fully
    b1_hands = Hand.objects.filter(board__id=1)
    assert b1_hands.count() == 2
    for h in b1_hands:
        play_out_hand(h)
    # play only one hand of board 2
    b2_hands = Hand.objects.filter(board__id=2)
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
    for u in all_users:
        for h in Hand.objects.filter(board__display_number=1):
            assert _error_response_or_viewfunc(h, u) == _everything_read_only_view, f"{u.username}"

    # Board 2 has been only partially played.
    for h in Hand.objects.exclude(board__display_number=1):
        for u in all_users:
            hand_description = (
                f"{u.username=} at {h} ({h.is_complete=}) with {[p.name for p in h.players()]}"
            )

            def expect(expected):
                __tracebackhide__ = True
                actual = _error_response_or_viewfunc(h, u)
                if isinstance(expected, types.FunctionType):
                    if actual != expected:
                        pytest.fail(
                            f"{hand_description} expected {expected} but got {actual.__name__}"
                        )
                else:
                    if type(actual) is not expected:
                        pytest.fail(
                            f"{hand_description} expected {expected} but got {type(actual)} ({getattr(actual, '__name__', '?')})"
                        )

            if u in [p.user for p in h.players()]:
                if h.is_complete:
                    expect(_everything_read_only_view)
                else:
                    expect(_interactive_view)
            else:
                expect(HttpResponseForbidden)
