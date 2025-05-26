from typing import Any


from bridge.card import Suit
from bridge.contract import Bid

from django.http import HttpResponseRedirect
from django.urls import reverse


from .models import Hand, Player
from .testutils import set_auction_to
from .views.hand import everything_read_only_view


def test_final_score(usual_setup: Hand, rf: Any) -> None:
    h = usual_setup
    north = Player.objects.get_by_name("Jeremy Northam")

    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), h)

    request = rf.get("/woteva/", data={"pk": h.pk})
    request.user = north.user

    response = everything_read_only_view(request=request, pk=h.pk)
    assert isinstance(response, HttpResponseRedirect)

    assert response.status_code == 302
    assert response.url == reverse("app:hand-detail", args=[h.pk])
