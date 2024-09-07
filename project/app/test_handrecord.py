from itertools import chain
from typing import Any

import pytest
from bridge.card import Card
from bridge.card import Suit as libSuit
from bridge.contract import Bid as libBid
from bridge.contract import Pass as libPass

from .models import AuctionException, Board, Play, Player, Table
from .views.table import bidding_box_partial_view


def test_rejects_illegal_calls(usual_setup):
    t = Table.objects.first()

    h = t.current_handrecord
    caller = h.auction.allowed_caller()

    def next_caller(current_caller):
        table = h.auction.table
        return table.get_lho(current_caller)

    h.add_call_from_player(player=caller, call=libBid.deserialize("Pass"))
    caller = next_caller(caller)

    one_notrump = libBid.deserialize("1N")
    assert one_notrump is not None
    h.add_call_from_player(player=caller, call=one_notrump)
    caller = next_caller(caller)

    with pytest.raises(AuctionException):
        h.add_call_from_player(player=caller, call=libBid.deserialize("1N"))

    h.add_call_from_player(player=caller, call=libBid.deserialize("Double"))

    assert t.handrecords.count() == 1  # we've only played one hand at this table

    the_hand_record = t.handrecords.first()

    calls = the_hand_record.calls.all()

    assert "Pass" in str(calls[0])
    assert "one notrump" in str(calls[1])
    assert "Double" in str(calls[2])


def set_auction_to(bid, table):
    h = table.current_handrecord

    def next_caller(current_caller):
        table = h.auction.table
        return table.get_lho(current_caller)

    caller = h.auction.allowed_caller()
    h.add_call_from_player(player=caller, call=bid)
    caller = next_caller(caller)

    h.add_call_from_player(player=caller, call=libPass)
    caller = next_caller(caller)

    h.add_call_from_player(player=caller, call=libPass)
    caller = next_caller(caller)

    h.add_call_from_player(player=caller, call=libPass)


def test_cards_by_player(usual_setup):
    t = Table.objects.first()
    set_auction_to(libBid(level=1, denomination=libSuit.CLUBS), t)

    before = set(chain.from_iterable(t.current_cards_by_seat.values()))
    Play.objects.create(hand=t.current_handrecord, serialized="c2")
    t.refresh_from_db()

    # TODO -- check that the card was played from the correct hand.
    after = set(chain.from_iterable(t.current_cards_by_seat.values()))
    club_two = Card(suit=libSuit.CLUBS, rank=2)
    assert before - after == set([club_two])


def _count_buttons(t: Table, request: Any) -> tuple[int, int]:
    response = bidding_box_partial_view(request, t.pk)
    response.render()

    disabled_buttons = []
    active_buttons = []
    bb_html_lines = response.content.decode().split("\n")

    for line in bb_html_lines:
        if "<button" not in line:
            continue
        if " disabled" in line:
            disabled_buttons.append(line)
        else:
            active_buttons.append(line)

    return len(disabled_buttons), len(active_buttons)


def test_bidding_box_html(usual_setup, rf):
    # First case: completed auction, contract is one diamond, not doubled.
    t = Table.objects.first()

    set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), t)
    request = rf.get("/woteva/", data={"table_pk": t.pk})
    request.user = Player.objects.get_by_name("Alice").user

    response = bidding_box_partial_view(request, t.pk)
    response.render()

    assert b"No bidding box" in response.content
    assert b"<button" not in response.content

    t.handrecord_set.all().delete()
    h = t.handrecord_set.create(board=Board.objects.first())

    # Second case: auction in progress, only call is one diamond.
    caller = h.auction.allowed_caller()

    h.add_call_from_player(player=caller, call=libBid(level=1, denomination=libSuit.DIAMONDS))
    disabled, _ = _count_buttons(t, request)
    assert disabled == 3

    # Third case: as above but with one more "Pass".
    caller = h.auction.allowed_caller()

    h.add_call_from_player(player=caller, call=libPass)

    caller = h.auction.allowed_caller()
    # you cannot double your own partner.
    disabled, active = _count_buttons(t, request)

    assert (disabled, active) == (38, 0), f"{caller=} should not be allowed to call at all"


def test_current_trick(usual_setup):
    t = Table.objects.first()
    h = t.current_handrecord

    # Nobody done played nothin'
    assert not h.current_trick

    set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), t)
    declarer = h.declarer
    first_players_seat = declarer.seat.lho()
    first_player = t[first_players_seat]

    # Does this dude even *have* the two of clubs? Beats me :-)
    club_two = Card(suit=libSuit.CLUBS, rank=2)
    h.add_play_from_player(player=first_player, card=club_two)
    assert len(h.current_trick) == 1
    which, where, what = h.current_trick[0]
    assert what.serialized == club_two.serialize()
