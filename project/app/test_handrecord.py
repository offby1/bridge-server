import re

from bridge.card import Suit
from bridge.contract import Bid, Pass

from .models import Call, Play, Table
from .views.table import _bidding_box


def test_watever(usual_setup):
    t = Table.objects.first()

    h = t.current_handrecord
    h.call_set.create(serialized="Pass")
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


def test_bidding_box_html(usual_setup):
    t = Table.objects.first()
    set_auction_to(Bid(level=1, denomination=Suit.DIAMONDS), t)

    def button_text(html_button_line):
        if (m := re.search(r">([^<]*?)</button>", html_button_line)) is not None:
            return m.group(1)

    disabled_buttons = []
    bb_html_lines = _bidding_box(t).split("\n")
    for line in bb_html_lines:
        if " disabled" in line:
            disabled_buttons.append(button_text(line))

    assert set(disabled_buttons) == {"1♣", "1♦", "Redouble"}
