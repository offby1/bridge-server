import re
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


def test_for_more_smoke(usual_setup, rf) -> None:
    t: Table | None = Table.objects.first()
    assert t is not None

    t = set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t)

    # all players have just one suit, so it's easy to play all the cards
    while True:
        assert t is not None
        legal_cards = t.current_hand.get_xscript().legal_cards()
        if not legal_cards:
            break
        chosen_card = legal_cards[0]

        t.current_hand.add_play_from_player(
            player=t.current_hand.get_xscript().player, card=chosen_card
        )
        t = Table.objects.get(pk=t.pk)

    request = rf.get("/woteva/")
    north = Player.objects.get_by_name("Jeremy Northam")
    request.user = north.user
    response = hand_archive_view(request=request, pk=t.current_hand.pk).render()
    distinct_spans = set()
    for line in response.content.decode().split("\n"):
        if (span := re.search(r"""played <span style=".*">..</span>""", line)) is not None:
            distinct_spans.add(span.group(0))

    assert len(distinct_spans) == 52


def test_final_score(usual_setup: None, rf: Any) -> None:
    north = Player.objects.get_by_name("Jeremy Northam")

    t = Table.objects.first()
    assert t is not None

    t = set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t)

    request = rf.get("/woteva/", data={"pk": t.pk})
    request.user = north.user

    response = hand_archive_view(request=request, pk=t.current_hand.pk)

    assert response.status_code == 302
    assert response.url == reverse("app:hand-detail", args=[t.current_hand.pk])
