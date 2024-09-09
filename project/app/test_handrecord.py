from __future__ import annotations

from itertools import chain
from typing import Any

import pytest
from bridge.card import Card
from bridge.card import Suit as libSuit
from bridge.contract import Bid as libBid
from bridge.contract import Pass as libPass
from bridge.seat import Seat as libSeat

from .models import AuctionException, Board, Play, Player, Table
from .testutils import set_auction_to
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


def test_cards_by_player(usual_setup):
    t = Table.objects.first()
    set_auction_to(libBid(level=1, denomination=libSuit.CLUBS), t)
    assert t.current_auction.declarer.seat == libSeat.NORTH

    before = set(chain.from_iterable(t.current_cards_by_seat.values()))
    Play.objects.create(hand=t.current_handrecord, serialized="d2")
    t.refresh_from_db()

    # TODO -- check that the card was played from the correct hand.
    after = set(chain.from_iterable(t.current_cards_by_seat.values()))
    diamond_two = Card(suit=libSuit.DIAMONDS, rank=2)
    assert before - after == {diamond_two}


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

    # TODO -- add a "lho" method to model.Player
    first_players_seat = declarer.seat.lho()
    first_player = t[first_players_seat]
    first_players_cards = first_player.hand.cards

    second_player = t[first_players_seat.lho()]
    second_players_cards = second_player.hand.cards

    first_card = first_players_cards[0]
    h.add_play_from_player(player=first_player, card=first_card)
    assert len(h.current_trick) == 1
    which, where, what = h.current_trick[-1]
    assert what == first_card

    second_card = second_players_cards[0]
    h.add_play_from_player(player=second_player, card=second_card)
    assert len(h.current_trick) == 2
    which, where, what = h.current_trick[-1]
    assert what == second_card


def test_next_seat_to_play(usual_setup):
    t = Table.objects.first()
    h = t.current_handrecord

    assert t.next_seat_to_play is None, "There's been no auction, so nobody can play"

    set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), t)

    assert h.declarer.seat == libSeat.NORTH
    assert t.next_seat_to_play.named_direction == "EAST"
