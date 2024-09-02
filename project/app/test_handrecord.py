import re

import pytest
from bridge.card import Suit
from bridge.contract import Bid, Pass

from .models import AuctionException, Board, Call, Play, Table
from .views.table import _bidding_box


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


def collect_disabled_buttons(t):
    disabled_buttons = []
    bb_html_lines = _bidding_box(t).split("\n")
    for line in bb_html_lines:
        if " disabled" in line:
            m = re.search(r">([^<]*?)</button>", line)
            button_text = m.group(1)

            disabled_buttons.append(button_text)

    return disabled_buttons


def test_bidding_box_html(usual_setup):
    # First case: completed auction, contract is one diamond, not doubled.
    t = Table.objects.first()

    set_auction_to(Bid(level=1, denomination=Suit.DIAMONDS), t)
    assert len(collect_disabled_buttons(t)) == 38

    t.handrecord_set.all().delete()
    t.handrecord_set.create(board=Board.objects.first())

    # Second case: auction in progress, only call is one diamond.
    Call.objects.create(
        hand=t.current_handrecord, serialized=Bid(level=1, denomination=Suit.DIAMONDS).serialize()
    )
    assert set(collect_disabled_buttons(t)) == {"1♣", "1♦", "Redouble"}

    # Third case: as above but with one more "Pass".
    Call.objects.create(hand=t.current_handrecord, serialized=Pass.serialize())

    # you cannot double your own partner.
    assert set(collect_disabled_buttons(t)) == {"1♣", "1♦", "Redouble", "Double"}
