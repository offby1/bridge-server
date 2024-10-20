from typing import Any

from bridge.card import Suit
from bridge.contract import Bid
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse

from .models import Player, Table
from .testutils import set_auction_to
from .views.hand import _four_hands_context_for_hand, hand_archive_view


def test_archive_view(usual_setup: None, rf: Any) -> None:
    t: Table | None = Table.objects.first()
    assert t is not None
    request = rf.get("/woteva/", data={"pk": t.pk})
    request.user = AnonymousUser()
    # We're just testing for the absence of an exception
    _four_hands_context_for_hand(request=request, hand=t.current_hand, as_dealt=True)


def test_final_score(usual_setup: None, rf: Any) -> None:
    north = Player.objects.get_by_name("Jeremy Northam")

    t = Table.objects.first()
    assert t is not None

    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t.current_hand)

    request = rf.get("/woteva/", data={"pk": t.pk})
    request.user = north.user

    response = hand_archive_view(request=request, pk=t.current_hand.pk)

    assert response.status_code == 302
    assert response.url == reverse("app:hand-detail", args=[t.current_hand.pk])
