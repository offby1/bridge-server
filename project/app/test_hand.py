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

from .models import AuctionError, Board, Hand, Play, Player, Table
from .testutils import set_auction_to
from .views.hand import _bidding_box_context_for_hand, bidding_box_partial_view

if TYPE_CHECKING:
    from django.template.response import TemplateResponse


def test_keeps_accurate_transcript(usual_setup) -> None:
    t: Table = Table.objects.first()  # type: ignore
    assert t is not None
    t = set_auction_to(libBid(level=1, denomination=libSuit.CLUBS), t)

    h: Hand = t.current_hand
    assert len(h.get_xscript().tricks) == 0

    declarer = h.declarer
    assert declarer is not None
    first_players_seat = declarer.seat.lho()
    first_player = h.players_by_direction[first_players_seat.value].libraryThing
    first_players_cards = first_player.hand.cards
    print(f"{first_players_cards=}")
    first_card = first_players_cards[0]

    h.add_play_from_player(player=first_player, card=first_card)
    assert len(h.get_xscript().tricks) == 1
    first_trick = h.get_xscript().tricks[0]
    first_play = first_trick.plays[0]
    assert first_play.card == first_card

    # I don't check that the two player's *hands* are equal because the library is stupid
    assert first_play.seat == first_player.seat
    assert len(h.players_remaining_cards(player=first_player).cards) == 12
    assert first_play.card not in h.players_remaining_cards(player=first_player).cards


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

    before = set(chain.from_iterable(t.current_hand.current_cards_by_seat().values()))
    Play.objects.create(hand=t.current_hand, serialized="d2")
    t = Table.objects.get(pk=t.pk)

    # TODO -- check that the card was played from the correct hand.
    after = set(chain.from_iterable(t.current_hand.current_cards_by_seat().values()))
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

    response = bidding_box_partial_view(request, t.current_hand.pk)
    response.render()
    return response


def _partition_button_values(bb_html: str) -> tuple[list[str], list[str]]:
    disabled_buttons: list[str] = []
    active_buttons: list[str] = []
    bb_html_lines = bb_html.split("\n")

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


def test_bidding_box_html(usual_setup, rf) -> None:
    # First case: completed auction, contract is one diamond, not doubled.
    t = Table.objects.first()
    assert t is not None
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

    east = Player.objects.get_by_name("Clint Eastwood")
    request = rf.get("/woteva/")
    request.user = east.user
    bbc_html = _bidding_box_context_for_hand(request, t.current_hand)["bidding_box_buttons"]
    disabled, _active = _partition_button_values(bbc_html)
    assert set(disabled) == {"1♣", "1♦", "Redouble"}

    # Third case: as above but with one more "Pass".
    t.current_hand.add_call_from_player(
        player=t.current_hand.auction.allowed_caller(),
        call=libPass,
    )

    t = Table.objects.get(pk=t.pk)
    assert t.current_auction.allowed_caller().name == "J.D. Souther"

    south = Player.objects.get_by_name("J.D. Souther")
    request.user = south.user
    bbc_html = _bidding_box_context_for_hand(request, t.current_hand)["bidding_box_buttons"]
    # you cannot double your own partner.
    disabled, _active = _partition_button_values(bbc_html)

    assert set(disabled) == {
        "1♣",
        "1♦",
        "Double",
        "Redouble",
    }
    request.user = east.user
    bbc_html = _bidding_box_context_for_hand(request, t.current_hand)["bidding_box_buttons"]

    disabled, _active = _partition_button_values(bbc_html)
    assert len(disabled) == 38, f"{east} shouldn't be allowed to call at all"


def test_current_trick(usual_setup) -> None:
    t = Table.objects.first()
    assert t is not None

    # Nobody done played nothin'
    assert not t.current_hand.current_trick

    t = set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), t)
    declarer = t.current_hand.declarer
    assert declarer is not None
    # TODO -- add a "lho" method to model.Player
    first_players_seat = declarer.seat.lho()
    first_player = t.current_hand.players_by_direction[first_players_seat.value].libraryThing
    first_players_cards = first_player.hand.cards

    second_player = t.current_hand.players_by_direction[first_players_seat.lho().value].libraryThing
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


def test_next_seat_to_play(usual_setup) -> None:
    t = Table.objects.first()
    assert t is not None

    assert t.next_seat_to_play is None, "There's been no auction, so nobody can play"

    t = set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), t)
    h = t.current_hand

    assert h.declarer.seat == libSeat.NORTH
    assert t.next_seat_to_play.named_direction == "EAST"
