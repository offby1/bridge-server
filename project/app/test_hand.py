from __future__ import annotations

import collections
import enum
from typing import TYPE_CHECKING, Any

import pytest
from bridge.card import Card, Rank
from bridge.card import Suit as libSuit
from bridge.contract import Bid as libBid
from bridge.contract import Pass as libPass
from bridge.seat import Seat as libSeat
from bridge.table import Player as libPlayer

from .models import AuctionError, Board, Hand, Player, Table, board, hand
from .testutils import set_auction_to
from .views.hand import (
    _bidding_box_context_for_hand,
    _maybe_redirect_or_error,
    bidding_box_partial_view,
)

if TYPE_CHECKING:
    from django.template.response import TemplateResponse


def test_keeps_accurate_transcript(usual_setup) -> None:
    t: Table = Table.objects.first()  # type: ignore
    assert t is not None
    set_auction_to(libBid(level=1, denomination=libSuit.CLUBS), t.current_hand)

    h: Hand = t.current_hand
    assert len(h.get_xscript().tricks) == 0

    declarer = h.declarer
    assert declarer is not None
    first_players_seat = declarer.seat.lho()
    first_player = h.players_by_direction[first_players_seat.value]
    first_players_cards = first_player.dealt_cards()

    first_card = first_players_cards[0]

    h.add_play_from_player(player=first_player.libraryThing(), card=first_card)
    h = Hand.objects.get(pk=h.pk)
    assert len(h.get_xscript().tricks) == 1
    first_trick = h.get_xscript().tricks[0]
    first_play = first_trick.plays[0]
    assert first_play.card == first_card

    # I don't check that the two player's *hands* are equal because the library is stupid
    assert first_play.seat == first_player.libraryThing().seat
    players_remaining_cards = h.players_remaining_cards(player=first_player.libraryThing()).cards
    assert players_remaining_cards is not None
    assert len(players_remaining_cards) == 12
    assert first_play.card not in players_remaining_cards


def test_rejects_illegal_calls(usual_setup):
    t = Table.objects.first()

    caller = t.current_hand.auction.allowed_caller()

    def next_caller(current_caller):
        table = t.current_hand.auction.table
        return table.get_lho(current_caller)

    t.current_hand.add_call_from_player(player=caller, call=libBid.deserialize("Pass"))

    caller = next_caller(caller)

    one_notrump = libBid.deserialize("1N")
    assert one_notrump is not None

    t.current_hand.add_call_from_player(player=caller, call=one_notrump)

    caller = next_caller(caller)

    with pytest.raises(AuctionError):
        t.current_hand.add_call_from_player(player=caller, call=libBid.deserialize("1N"))

    t.current_hand.add_call_from_player(player=caller, call=libBid.deserialize("Double"))

    assert t.hand_set.count() == 1  # we've only played one hand at this table

    the_hand = t.hand_set.first()

    calls = the_hand.calls.all()

    assert "Pass" in str(calls[0])
    assert "one notrump" in str(calls[1])
    assert "Double" in str(calls[2])


def test_cards_by_player(usual_setup) -> None:
    t: Table | None = Table.objects.first()
    assert t is not None

    set_auction_to(libBid(level=1, denomination=libSuit.CLUBS), t.current_hand)
    assert t.current_auction.declarer is not None
    assert t.current_auction.declarer.seat == libSeat.NORTH

    east = Player.objects.get_by_name(name="Clint Eastwood")

    h: Hand = t.current_hand
    before = set(h.current_cards_by_seat()[libSeat.EAST])
    assert len(before) == 13  # just checkin' :-)

    diamond_two = Card(suit=libSuit.DIAMONDS, rank=Rank(2))
    h.add_play_from_player(player=east.libraryThing(), card=diamond_two)
    h = Hand.objects.get(pk=h.pk)

    after = set(h.current_cards_by_seat()[libSeat.EAST])
    assert before - after == {diamond_two}
    for seat in (libSeat.NORTH, libSeat.SOUTH, libSeat.WEST):
        assert len(h.current_cards_by_seat()[seat]) == 13


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
    set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), t.current_hand)
    # set_auction_to has set the declarer to be the dealer.

    assert t.current_auction.found_contract

    # The auction is settled, so no bidding box.
    response = _bidding_box_as_seen_by(t, t.current_hand.player_who_may_play, rf)
    assert b"<button" not in response.content

    # Second case: auction in progress, only call is one diamond.
    t.hand_set.all().delete()
    t.hand_set.create(board=Board.objects.first())

    assert t.current_auction.allowed_caller().name == "Jeremy Northam"

    from app.models import logged_queries

    t.current_hand.add_call_from_player(
        player=t.current_hand.auction.allowed_caller(),
        call=libBid(level=1, denomination=libSuit.DIAMONDS),
    )

    with logged_queries():
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

    set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), t.current_hand)
    declarer = t.current_hand.declarer
    assert declarer is not None
    # TODO -- add a "lho" method to model.Player
    first_players_seat = declarer.seat.lho()
    first_player = t.current_hand.players_by_direction[first_players_seat.value]
    first_players_cards = first_player.dealt_cards()

    second_player = t.current_hand.players_by_direction[first_players_seat.lho().value]
    second_players_cards = second_player.dealt_cards()

    first_card = first_players_cards[0]
    t.current_hand.add_play_from_player(player=first_player.libraryThing(), card=first_card)

    assert len(t.current_hand.current_trick) == 1
    tt = t.current_hand.current_trick[-1]
    assert tt.card == first_card

    second_card = second_players_cards[0]
    t.current_hand.add_play_from_player(player=second_player.libraryThing(), card=second_card)

    assert len(t.current_hand.current_trick) == 2
    tt = t.current_hand.current_trick[-1]
    assert tt.card == second_card


def test_next_seat_to_play(usual_setup) -> None:
    t = Table.objects.first()
    assert t is not None

    assert t.next_seat_to_play is None, "There's been no auction, so nobody can play"

    set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), t.current_hand)
    h = t.current_hand

    assert h.declarer.seat == libSeat.NORTH
    assert t.next_seat_to_play is not None
    assert t.next_seat_to_play.named_direction == "East"


def test_sends_message_on_auction_completed(usual_setup, monkeypatch) -> None:
    t = Table.objects.first()
    assert t is not None

    sent_events_by_channel: dict[str, list[Any]] = collections.defaultdict(list)

    def send_event(*, channel, event_type, data):
        sent_events_by_channel[channel].append(data)

    monkeypatch.setattr(hand, "send_event", send_event)
    set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), t.current_hand)

    first_player = Player.objects.first()
    assert first_player is not None
    assert any("contract" in e for e in sent_events_by_channel[f"system:player:{first_player.pk}"])


class HandIsComplete(enum.Enum):
    incomplete = 0
    complete = 1


class RequestedPage(enum.StrEnum):
    detail = "app:hand-detail"
    archive = "app:hand-archive"


@pytest.mark.parametrize(
    ("hand_is_complete", "player_visibility", "requested_page", "expected_result"),
    [
        (
            HandIsComplete.incomplete,
            Board.PlayerVisibility.everything,
            RequestedPage.detail,
            None,
        ),
        (
            HandIsComplete.incomplete,
            Board.PlayerVisibility.everything,
            RequestedPage.archive,
            302,
        ),
        (
            HandIsComplete.incomplete,
            Board.PlayerVisibility.nothing,
            RequestedPage.detail,
            403,
        ),
        (
            HandIsComplete.incomplete,
            Board.PlayerVisibility.nothing,
            RequestedPage.archive,
            403,
        ),
        (
            HandIsComplete.complete,
            Board.PlayerVisibility.everything,
            RequestedPage.detail,
            302,
        ),
        (
            HandIsComplete.complete,
            Board.PlayerVisibility.everything,
            RequestedPage.archive,
            None,
        ),
        (
            HandIsComplete.complete,
            Board.PlayerVisibility.nothing,
            RequestedPage.detail,
            403,
        ),
        (
            HandIsComplete.complete,
            Board.PlayerVisibility.nothing,
            RequestedPage.archive,
            403,
        ),
    ],
)
def test_exhaustive_archive_and_detail_redirection(
    rf,
    hand_is_complete,
    player_visibility,
    requested_page,
    expected_result,
):
    actual_result = _maybe_redirect_or_error(
        hand_is_complete=hand_is_complete.value,
        hand_pk=123,
        player_visibility=player_visibility,
        request_viewname=requested_page.value,
    )
    if actual_result is None:
        assert expected_result is None
    else:
        assert actual_result.status_code == expected_result


@pytest.mark.django_db
def test_predictable_shuffles():
    attrs1_empty = board.board_attributes_from_display_number(display_number=1, rng_seeds=[])
    attrs2_empty = board.board_attributes_from_display_number(display_number=2, rng_seeds=[])

    # Same  'cuz we used the same random seeds
    for k in ("north_cards", "east_cards", "south_cards", "west_cards"):
        assert attrs1_empty[k] == attrs2_empty[k]

    attrs1_golly = board.board_attributes_from_display_number(
        display_number=1, rng_seeds=[b"golly"]
    )

    for k in ("ns_vulnerable", "ew_vulnerable", "dealer"):
        assert attrs1_empty[k] == attrs1_golly[k]

    # Cards are different
    for k in ("north_cards", "east_cards", "south_cards", "west_cards"):
        assert attrs1_empty[k] != attrs1_golly[k]
