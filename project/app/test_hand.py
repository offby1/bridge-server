from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING

import pytest
from bridge.card import Card
from bridge.card import Suit as libSuit
from bridge.contract import Bid as libBid
from bridge.contract import Pass as libPass
from bridge.seat import Seat as libSeat
from bridge.table import Player as libPlayer

from .models import AuctionError, Board, Play, Player, Table
from .testutils import set_auction_to
from .views.table import bidding_box_partial_view

if TYPE_CHECKING:
    from django.template.response import TemplateResponse


def test_rejects_illegal_calls(usual_setup):
    t = Table.objects.first()

    caller = t.current_hand.auction.allowed_caller()

    def next_caller(current_caller):
        table = t.current_hand.auction.table
        return table.get_lho(current_caller)

    t.current_hand.add_call_from_player(player=caller, call=libBid.deserialize("Pass"))
    t = Table.objects.get(pk=t.pk)

    caller = next_caller(caller)

    one_notrump = libBid.deserialize("1N")
    assert one_notrump is not None

    t.current_hand.add_call_from_player(player=caller, call=one_notrump)
    t = Table.objects.get(pk=t.pk)

    caller = next_caller(caller)

    with pytest.raises(AuctionError):
        t.current_hand.add_call_from_player(player=caller, call=libBid.deserialize("1N"))

    t.current_hand.add_call_from_player(player=caller, call=libBid.deserialize("Double"))
    t = Table.objects.get(pk=t.pk)

    assert t.hand_set.count() == 1  # we've only played one hand at this table

    the_hand = t.hand_set.first()

    calls = the_hand.calls.all()

    assert "Pass" in str(calls[0])
    assert "one notrump" in str(calls[1])
    assert "Double" in str(calls[2])


def test_cards_by_player(usual_setup):
    t = Table.objects.first()
    t = set_auction_to(libBid(level=1, denomination=libSuit.CLUBS), t)

    assert t.current_auction.declarer.seat == libSeat.NORTH

    before = set(chain.from_iterable(t.current_cards_by_seat().values()))
    Play.objects.create(hand=t.current_hand, serialized="d2")
    t = Table.objects.get(pk=t.pk)

    # TODO -- check that the card was played from the correct hand.
    after = set(chain.from_iterable(t.current_cards_by_seat().values()))
    diamond_two = Card(suit=libSuit.DIAMONDS, rank=2)
    assert before - after == {diamond_two}


def _bidding_box_as_seen_by(t: Table, as_seen_by: Player | libPlayer, rf) -> TemplateResponse:
    from app.models.utils import assert_type

    if isinstance(as_seen_by, libPlayer):
        as_seen_by = Player.objects.get_by_name(as_seen_by.name)
    assert_type(as_seen_by, Player)
    assert isinstance(as_seen_by, Player)

    request = rf.get("/woteva/", data={"table_pk": t.pk})
    request.user = as_seen_by.user

    response = bidding_box_partial_view(request, t.pk)
    response.render()
    return response


def _partition_button_values(t: Table, as_seen_by: Player, rf) -> tuple[list[str], list[str]]:
    response = _bidding_box_as_seen_by(t, as_seen_by, rf)

    disabled_buttons: list[str] = []
    active_buttons: list[str] = []
    bb_html_lines = response.content.decode().split("\n")

    def value(html: str) -> str:
        import re

        m = re.search(r'value="(.*?)"', html)
        assert m is not None, html
        return m.group(1)

    for line in bb_html_lines:
        if "<button" not in line:
            continue
        if " disabled" in line:
            disabled_buttons.append(value(line))
        else:
            active_buttons.append(value(line))

    return disabled_buttons, active_buttons


def test_bidding_box_html(usual_setup, rf):
    # First case: completed auction, contract is one diamond, not doubled.
    t = Table.objects.first()

    t = set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), t)
    # set_auction_to has set the declarer to be the dealer.

    assert t.current_auction.found_contract

    # The auction is settled, so no bidding box.
    response = _bidding_box_as_seen_by(t, t.current_auction.allowed_caller(), rf)
    assert b"<button" not in response.content

    # Second case: auction in progress, only call is one diamond.
    t.hand_set.all().delete()
    t.hand_set.create(board=Board.objects.first())
    t = Table.objects.get(pk=t.pk)

    assert t.current_auction.allowed_caller().name == "Jeremy Northam"

    from app.models import logged_queries

    t.current_hand.add_call_from_player(
        player=t.current_hand.auction.allowed_caller(),
        call=libBid(level=1, denomination=libSuit.DIAMONDS),
    )

    with logged_queries():
        t = Table.objects.get(pk=t.pk)  # like refresh_from_db, but updates all the relations too

        assert t.current_auction.allowed_caller().name == "Clint Eastwood"

    disabled, enabled = _partition_button_values(
        t, as_seen_by=t.current_hand.auction.allowed_caller(), rf=rf
    )
    assert set(disabled) == {"1♣", "1♦", "Redouble"}

    # Third case: as above but with one more "Pass".
    t.current_hand.add_call_from_player(
        player=t.current_hand.auction.allowed_caller(),
        call=libPass,
    )

    t = Table.objects.get(pk=t.pk)
    assert t.current_auction.allowed_caller().name == "J.D. Souther"

    # you cannot double your own partner.
    disabled, active = _partition_button_values(
        t, as_seen_by=t.current_hand.auction.allowed_caller(), rf=rf
    )

    assert set(disabled) == {
        "1♣",
        "1♦",
        "Double",
        "Redouble",
    }
    esther = Player.objects.get_by_name("Clint Eastwood")
    disabled, active = _partition_button_values(t, as_seen_by=esther, rf=rf)
    assert len(disabled) == 38, f"{esther} shouldn't be allowed to call at all"


def test_current_trick(usual_setup):
    t = Table.objects.first()

    # Nobody done played nothin'
    assert not t.current_hand.current_trick

    t = set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), t)
    declarer = t.current_hand.declarer

    # TODO -- add a "lho" method to model.Player
    first_players_seat = declarer.seat.lho()
    first_player = t.modPlayer_by_seat(first_players_seat).libraryThing
    first_players_cards = first_player.hand.cards

    second_player = t.modPlayer_by_seat(first_players_seat.lho()).libraryThing
    second_players_cards = second_player.hand.cards

    first_card = first_players_cards[0]
    t.current_hand.add_play_from_player(player=first_player, card=first_card)
    t = Table.objects.get(pk=t.pk)
    assert len(t.current_hand.current_trick) == 1
    which, where, what, winner = t.current_hand.current_trick[-1]
    assert what == first_card

    second_card = second_players_cards[0]
    t.current_hand.add_play_from_player(player=second_player, card=second_card)
    t = Table.objects.get(pk=t.pk)
    assert len(t.current_hand.current_trick) == 2
    which, where, what, winner = t.current_hand.current_trick[-1]
    assert what == second_card


def test_next_seat_to_play(usual_setup):
    t = Table.objects.first()

    assert t.next_seat_to_play is None, "There's been no auction, so nobody can play"

    t = set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), t)
    h = t.current_hand

    assert h.declarer.seat == libSeat.NORTH
    assert t.next_seat_to_play.named_direction == "EAST"
