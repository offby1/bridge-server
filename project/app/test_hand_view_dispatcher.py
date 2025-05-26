import logging

import pytest

from app.models import Board, Hand, Player, Tournament


from app.views.hand import _error_response_or_viewfunc, _everything_read_only_view

from app.testutils import play_out_hand

logger = logging.getLogger()


@pytest.fixture
def two_hands(db) -> list[Hand]:
    t1 = Tournament.objects.create()
    b1, _ = Board.objects.get_or_create_from_display_number(
        display_number=1, tournament=t1, group="A"
    )
    North, South, East, West = [Player.objects.create_synthetic() for _ in range(4)]
    North.partner_with(South)
    East.partner_with(West)
    Ding, Dong, Witch, Dead = [Player.objects.create_synthetic() for _ in range(4)]
    Ding.partner_with(Dong)
    Witch.partner_with(Dead)
    h1 = Hand.objects.create(
        board=b1, North=North, East=East, West=West, South=South, table_display_number=1
    )
    h2 = Hand.objects.create(
        board=b1, North=Ding, East=Dong, West=Witch, South=Dead, table_display_number=2
    )
    play_out_hand(h1)

    return [h1, h2]


def test_dispatcher(two_hands: list[Hand], rf):
    h1, h2 = two_hands
    North = h1.North

    # North can "see" all of h1.
    request = rf.get("/woteva/", data={"pk": h1.pk})
    setattr(request, "session", {})
    request.user = North.user

    assert _error_response_or_viewfunc(h1, North.user) == _everything_read_only_view

    # North can also "see" all of h2, even though it's not complete.
    assert _error_response_or_viewfunc(h2, North.user) == _everything_read_only_view
