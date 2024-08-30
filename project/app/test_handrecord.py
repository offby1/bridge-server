import pytest

from .models import Table
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


def test_cards_by_player(usual_setup):
    t = Table.objects.first()
    before = t.current_cards_by_seat[Seat.NORTH]
    play = Play.objects.create(hand=wtf, serialized="c2")
    t.current_handrecord
    after = t.current_cards_by_seat[Seat.NORTH]


@pytest.mark.xfail(reason="WIP")
def test_bidding_box_html(usual_setup):
    t = Table.objects.first()
    bb_html = _bidding_box(t)
    assert "wow lookit all them bids" in bb_html
