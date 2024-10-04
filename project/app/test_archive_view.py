from typing import Any

from bridge.card import Suit
from bridge.contract import Bid
from django.contrib.auth.models import AnonymousUser

from .models import Player, Table
from .testutils import set_auction_to
from .views.table.archive import hand_archive_view
from .views.table.details import _four_hands_context_for_table


def test_archive_view(usual_setup: None, rf: Any) -> None:
    t: Table | None = Table.objects.first()
    assert t is not None
    request = rf.get("/woteva/", data={"pk": t.pk})
    request.user = AnonymousUser()
    # We're just testing for the absence of an exception
    _four_hands_context_for_table(request, t, as_dealt=True)


def test_final_score(usual_setup: None, rf: Any) -> None:
    north = Player.objects.get_by_name("Jeremy Northam")

    t = Table.objects.first()
    assert t is not None

    t = set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t)

    request = rf.get("/woteva/", data={"pk": t.pk})
    request.user = north.user

    response = hand_archive_view(request, t.pk)

    assert response.status_code == 404
    assert b"not been completely played" in response.content
