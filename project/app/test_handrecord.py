import re

import pytest
from bridge.card import Suit
from bridge.contract import Bid, Pass

from .models import AuctionException, Board, Call, Play, Player, Table
from .views.table import bidding_box_partial_view


def test_watever(usual_setup):
    t = Table.objects.first()

    h = t.current_handrecord
    h.call_set.create(serialized="Pass")
    h.call_set.create(serialized="1NT")
    with pytest.raises(AuctionException):
        h.call_set.create(serialized="1NT")

    h.call_set.create(serialized="Double")

    assert t.handrecords.count() == 1  # we've only played one hand at this table

    the_hand_record = t.handrecords.first()

    calls = the_hand_record.calls.all()

    assert "Pass" in str(calls[0])
    assert "one notrump" in str(calls[1])
    assert "Double" in str(calls[2])


def set_auction_to(bid, table):
    Call.objects.create(hand=table.current_handrecord, serialized=bid.serialize())
    Call.objects.create(hand=table.current_handrecord, serialized=Pass.serialize())
    Call.objects.create(hand=table.current_handrecord, serialized=Pass.serialize())
    Call.objects.create(hand=table.current_handrecord, serialized=Pass.serialize())


def test_cards_by_player(usual_setup):
    t = Table.objects.first()
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t)

    first_seat = t.seat_set.first()

    before = t.current_cards_by_seat[first_seat]
    Play.objects.create(hand=t.current_handrecord, serialized="c2")
    t.refresh_from_db()
    after = t.current_cards_by_seat[first_seat]
    assert before != after


def _collect_disabled_buttons(t, request):
    response: TemplateResponse = bidding_box_partial_view(request, t.pk)
    response.render()

    disabled_buttons = []
    bb_html_lines = response.content.decode().split("\n")

    for line in bb_html_lines:
        if " disabled" in line:
            m = re.search(r">([^<]*?)</button>", line)
            button_text = m.group(1)

            disabled_buttons.append(button_text)

    return disabled_buttons


def test_bidding_box_html(usual_setup, rf):
    # First case: completed auction, contract is one diamond, not doubled.
    t = Table.objects.first()

    set_auction_to(Bid(level=1, denomination=Suit.DIAMONDS), t)
    request = rf.get("/woteva/", data={"table_pk": t.pk})
    request.user = Player.objects.get_by_name("Alice").user

    response = bidding_box_partial_view(request, t.pk)
    assert b"No bidding box" in response.content
    assert b"<button" not in response.content

    t.handrecord_set.all().delete()
    t.handrecord_set.create(board=Board.objects.first())

    # Second case: auction in progress, only call is one diamond.
    Call.objects.create(
        hand=t.current_handrecord, serialized=Bid(level=1, denomination=Suit.DIAMONDS).serialize()
    )
    assert set(_collect_disabled_buttons(t, request)) == {"1♣", "1♦", "Redouble"}

    # Third case: as above but with one more "Pass".
    Call.objects.create(hand=t.current_handrecord, serialized=Pass.serialize())

    # you cannot double your own partner.
    assert set(_collect_disabled_buttons(t, request)) == {"1♣", "1♦", "Redouble", "Double"}
